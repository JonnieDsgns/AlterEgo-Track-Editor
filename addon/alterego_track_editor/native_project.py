"""Native track graph with stable layer provenance and copy-preserving updates.

Uses the bundled TrackView codecs. No engine/runtime code or installation API.
"""
from collections import defaultdict
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import zipfile
from .native.storage import Catalog
from .native.formats.pkg import Document, plain
from .native.formats.pkg_tree import Tree, patch_edits, float32
from .native.scene import IDENTITY, render_transform
from .native.geometry import mesh, terrain_info, triangles, combine
from . import variants

# Static visual props only: functional components (grid, garages, cameras, audio,
# lights, triggers, physics) carry identities that a plain copy would duplicate.
CLONE_COMPONENTS = {'Model', 'Render', 'WorldObject'}
CLONE_FIELDS = {'name', 'overrides', 'template', 'uniqueid'}
INSERT_LIMITS = ('Visual placement only: no collision, precomputed visibility (PVS) or lightmap '
                 'bake data is generated; source Render fields are copied unchanged.')


def digest(data):
    return hashlib.sha256(data).hexdigest()


# Numbered race placements, in the order Swofty Custom Grid Size extends them
# (packages/core/src/activation/grid.rs): garages reference pit-garage uniqueids.
RACE_KINDS = ('PitGarage', 'F1Garage', 'PitBox', 'GridSlot')
RACE_NAME = re.compile(r'(.*\$)?(PitGarage|F1Garage|PitBox|GridSlot)([0-9]+)')


def race_reason(doc, index, item):
    """Why an instance cannot seed a new numbered grid slot/pit box/garage, or None."""
    match = RACE_NAME.fullmatch(str(item.get('name', '')))
    if not match:
        return 'Not a numbered grid slot, pit box or garage'
    overrides = item.get('overrides', {})
    leaf = lambda *path: getattr(doc.leaves.get(('instances', index) + path), 'type', None)
    if set(item) != CLONE_FIELDS or leaf('uniqueid') != 'woid' or leaf('overrides', 'WorldObject', 'transform') != 'mat4':
        return 'Unexpected race placement fields'
    if match.group(2) == 'F1Garage':
        garage = overrides.get('F1Garage', {})
        if item['template'] != 'F1Garage' or set(overrides) != {'F1Garage', 'WorldObject'} or \
                set(garage) != {'id', 'left car placement', 'right car placement'} or leaf('overrides', 'F1Garage', 'id') != 'si32' or \
                {leaf('overrides', 'F1Garage', k) for k in ('left car placement', 'right car placement')} != {'woid'}:
            return 'Unexpected garage layout'
    else:
        placement = overrides.get('VehPlacement', {})
        if item['template'] != 'VehiclePlacement' or set(overrides) != {'VehPlacement', 'WorldObject'} or \
                set(placement) != {'Group', 'Id'} or leaf('overrides', 'VehPlacement', 'Id') != 'ui32':
            return 'Unexpected vehicle placement layout; choose a numbered source with an explicit Id'
    return None


def clone_reason(doc, index, item):
    """Why an existing instance cannot be duplicated, or None when it is a supported static prop."""
    overrides = item.get('overrides', {})
    leaf = lambda *path: doc.leaves.get(('instances', index) + path)
    if set(item) != CLONE_FIELDS:
        return 'Unsupported instance fields'
    if item.get('template') != 'RenderModel':
        return 'Only RenderModel static props can be duplicated'
    if not isinstance(overrides, dict) or not {'Model', 'WorldObject'} <= set(overrides) or set(overrides) - CLONE_COMPONENTS:
        return 'Functional components need typed editors before duplication'
    if not str(overrides['Model'].get('model', '')).endswith('?context=render'):
        return 'Model reference is not a resolved render model'
    checks = (('uniqueid',), 'woid'), (('name',), 'stri'), (('overrides', 'WorldObject', 'transform'), 'mat4')
    if any(getattr(leaf(*path), 'type', None) != typ for path, typ in checks):
        return 'Unexpected native identity/transform field types'
    if ']' in item['name']:
        return 'Name cannot be addressed by launcher selectors'
    return None


class TrackDocument:
    def __init__(self, source, base=None):
        self.source = Path(source).expanduser().resolve()
        self.catalog = Catalog()
        self.addon_scene = None
        self.package_temporary = None
        self.is_addon = self.source.is_file() or (self.source/'swofty.json').is_file()
        self.base = str(Path(base).resolve()) if base else ''
        if self.is_addon:
            from .native.addons import open_addon
            addon_source = self.source
            package_root = None
            if self.source.is_file():
                with zipfile.ZipFile(self.source) as z:
                    raw_package = 'manifest.json' in z.namelist() and 'swofty.json' not in z.namelist()
                if raw_package:
                    from .native.addons import contained
                    self.package_temporary = tempfile.TemporaryDirectory(prefix='ate-track-package-')
                    wrapper = Path(self.package_temporary.name)
                    package_root = wrapper/'track'
                    package_root.mkdir()
                    with zipfile.ZipFile(self.source) as z:
                        if len(z.infolist())>20000 or sum(i.file_size for i in z.infolist())>4*1024**3:
                            raise ValueError('Track package exceeds budget')
                        seen=set()
                        for info in z.infolist():
                            file=contained(package_root,info.filename)
                            if file in seen or (info.external_attr>>16)&0o170000==0o120000:
                                raise ValueError('Duplicate or symlinked track package member')
                            seen.add(file)
                            if info.is_dir():continue
                            if info.file_size>2*1024**3 or info.file_size>max(1024**2,info.compress_size*1000):
                                raise ValueError('Track package member exceeds budget')
                            file.parent.mkdir(parents=True,exist_ok=True)
                            with z.open(info) as src,file.open('xb') as dst:shutil.copyfileobj(src,dst,1024*1024)
                    (wrapper/'swofty.json').write_text(json.dumps({'name':'Track package','operations':{'assets':['assets.json']}}))
                    (wrapper/'assets.json').write_text(json.dumps({'ops':[{'op':'track.add','source':'track'}]}))
                    addon_source=wrapper
            self.addon_scene = open_addon(addon_source, base=base, catalog_only=True)
            self.catalog = self.addon_scene.catalog
            temporary = self.addon_scene._addon_temp[0]
            self.root = package_root or (Path(temporary.name) if temporary else self.source)
        else:
            self.root = self.source
            if not (self.root/'wep').is_dir():
                raise ValueError('Choose a native track folder containing wep, or a Swofty addon')
            common = self.root/'wep'/(self.root.name+'_common.erp')
            paths = [common] + sorted((self.root/'wep').glob('*.erp')) + sorted(self.root.glob('*.erp'))
            for p in dict.fromkeys(paths):
                if p.is_file():
                    self.catalog.mount(p)
            self.catalog.asset_roots = [self.root]
            game = next((p for p in self.root.parents if (p/'F1_25.exe').is_file()), None)
            if game:
                self.catalog.asset_roots.append(game)
        self.layers = {}
        self.warnings = list(self.addon_scene.warnings) if self.addon_scene else []
        self.worlds = {}
        # Resolve actual typed World resources, not guessed archive suffixes.
        for uri, (_, resource) in self.catalog.by_uri.items():
            if resource.type_name != 'World' or not uri.endswith('.wep') or '/tracks/' not in uri:
                continue
            prefix = uri.split('/tracks/', 1)[1]
            code = prefix.split('/', 1)[0]
            stem = uri.rsplit('/', 1)[-1][:-4]
            if not stem.startswith(code+'_'):
                continue
            key = stem[len(code)+1:]
            self.worlds[key] = {'uri': uri, 'code': code}
        if not self.worlds:
            raise ValueError('No native track worlds found')
        codes = {w['code'] for w in self.worlds.values()}
        if len(codes) != 1:
            raise ValueError('Multiple track namespaces require separate projects')
        self.code = codes.pop()
        self.layer_variants = defaultdict(set)
        for key, world in self.worlds.items():
            try:
                root = plain(Document(self.catalog.read(world['uri'])).root)
                for uri in root.get('layers', []):
                    self.layer_variants[uri].add(key)
            except (ValueError, KeyError) as exc:
                self.warnings.append({'world': key, 'reason': str(exc)})
        self.records = []
        self.names = set()
        self.unique_ids = set()
        self.layer_edits = {}
        self.inserted = []
        self.asset_resources = []
        self.asset_layers = set()
        self.deleted = []
        self._pvs_names = None
        self._references = None
        for uri, keys in sorted(self.layer_variants.items()):
            try:
                raw = self.catalog.read(uri)
                doc = Document(raw)
                self.layers[uri] = {'doc': doc, 'hash': digest(raw)}
                for index, item in enumerate(plain(doc.root).get('instances', [])):
                    self.names.add(item.get('name', ''))
                    uid = doc.leaves.get(('instances', index, 'uniqueid'))
                    if uid is not None:
                        self.unique_ids.add(uid.raw)
                    overrides = item.get('overrides', {})
                    world = overrides.get('WorldObject', {}).get('transform')
                    path = ('instances', index, 'overrides', 'WorldObject', 'transform')
                    model = overrides.get('Model', {}).get('model', '')
                    terrain = overrides.get('TerrainModel', {}).get('model', '')
                    transform = IDENTITY[:]
                    render_error = None
                    if model.endswith('?context=render'):
                        try:
                            transform = render_transform(self.catalog, model[:-len('?context=render')])
                        except (ValueError, KeyError) as exc:
                            render_error = str(exc)
                    identity = digest((uri+'\n'+str(index)+'\n'+str(item.get('uniqueid', ''))).encode())
                    self.records.append({'id': identity, 'layer': uri, 'index': index,
                        'name': item.get('name', 'Unnamed'), 'template': item.get('template', ''),
                        'variants': sorted(keys), 'world': world if world is not None else IDENTITY[:],
                        'render': transform, 'render_error': render_error, 'model': model,
                        'terrain': terrain, 'binding': overrides.get('Model', {}).get('mat binding'),
                        'physics': overrides.get('PhysicsTerrain',{}).get('terrain',''),
                        'editable': path in doc.leaves and doc.leaves[path].type == 'mat4',
                        'clone_reason': clone_reason(doc, index, item),
                        'race_reason': race_reason(doc, index, item),
                        'path': path, 'layer_hash': digest(raw)})
            except (ValueError, KeyError) as exc:
                self.warnings.append({'layer': uri, 'reason': str(exc)})
        self.by_id = {r['id']: r for r in self.records}
        self.geometry_cache = {}

    def geometry(self, record):
        if record['render_error']:
            raise ValueError(record['render_error'])
        model = record['model']
        if not model.endswith('?context=render'):
            return None
        uri = model[:-len('?context=render')]+'?lod=0&mesh'
        # Caller owns Blender shared meshes; retain at most one decoded payload here.
        if uri not in self.geometry_cache:
            self.geometry_cache.clear()
            self.geometry_cache[uri] = mesh(self.catalog, uri)
        return uri, self.geometry_cache[uri]

    def terrain_geometry(self, record):
        for cell, draw_index, position, ib, draw, normal, attrs, material in terrain_info(self.catalog.read(record['terrain'])):
            first, count, base, _ = draw
            g = combine([triangles(self.catalog, position, ib, first, count, base, normal, attrs)])
            g.groups = [{'first': 0, 'count': count, 'slot': material, 'material': material}]
            yield f'{record["terrain"]}#{cell}:{draw_index}', g

    def insert_name(self, source, identity, asset_name=None):
        base = source['name'] if asset_name is None else source['name'][:source['name'].rfind('$')+1]+asset_name
        name = f"{base}_ate_{identity[:12]}"
        if len(name.encode('utf-8')) > 255:
            raise ValueError('Generated placement name exceeds 255 bytes: '+source['name'])
        return name

    def apply(self, changes, insertions=(), deletions=(), retargets=None, allow_pvs_deletions=False):
        """Plan native placement edits; returns changed layer bytes.

        changes: {record id: 16 floats} for moved existing placements.
        insertions: [{'id': stable new identity, 'source': record id, 'world': 16 floats,
        optional 'asset': {'name', 'family', 'binding', 'resources'} from static_asset.build_asset}].
        The asset form clones the source entry but points its Model at the new family; the
        family resources are embedded beside the edited layer by write_updated/write_patch.
        deletions: record ids of static props to remove. retargets: {record id: asset} replaces
        an existing static prop's model/binding with an independent family.
        """
        plans = defaultdict(lambda: {'moves': [], 'clones': [], 'deletes': [], 'retargets': []})
        for identity, values in changes.items():
            r = self.by_id[identity]
            if not r['editable']:
                raise ValueError('Placement has no supported native WorldObject matrix: '+r['name'])
            if r['render_error']:
                raise ValueError('Cannot edit unresolved render placement: '+r['name'])
            plans[r['layer']]['moves'].append((r, list(values)))
        names, uids, inserted, assets = set(self.names), set(self.unique_ids), [], {}
        for identity, asset in sorted((retargets or {}).items()):
            r = self.by_id[identity]
            if r['clone_reason'] or r['render_error']:
                raise ValueError(f"{r['name']}: only static props can use an edited asset")
            plans[r['layer']]['retargets'].append((r, self._asset_fields(asset, assets)))
        deleted = []
        for identity in sorted(deletions):
            r = self.by_id.get(identity)
            if r is None:
                raise ValueError('Deleted placement is no longer in the native track')
            reason = self.deletion_reason(r, allow_pvs_deletions)
            if reason:
                raise ValueError(f"Cannot delete {r['name']}: {reason}")
            plans[r['layer']]['deletes'].append(r)
            deleted.append({'name': r['name'], 'layer': r['layer'], 'variants': r['variants'],
                            'pvs_listed': r['name'] in self.pvs_names()})
        race = [s for s in insertions if s.get('race')]
        for clone in self._race_clones(race, names, uids):
            plans[clone['source']['layer']]['clones'].append(clone)
            inserted.append({'name': clone['name'], 'uniqueid': clone['uniqueid'], 'source': clone['source']['name'],
                             'layer': clone['source']['layer'], 'variants': clone['source']['variants'], 'asset': None})
        for spec in sorted((s for s in insertions if not s.get('race')), key=lambda s: s['id']):
            source = self.by_id.get(spec['source'])
            if source is None:
                raise ValueError('Duplicated placement source is no longer in the native track')
            if source['clone_reason'] or source['render_error']:
                raise ValueError(f"{source['name']}: {source['clone_reason'] or source['render_error']}")
            asset = spec.get('asset')
            fields = {}
            if asset:
                fields = self._asset_fields(asset, assets)
            name = self.insert_name(source, spec['id'], asset and asset['name'])
            uid = hashlib.md5(f"alterego-track-editor:{self.code}:{source['layer']}:{name}".encode()).digest()
            if name in names or uid in uids:
                raise ValueError('New placement identity collides with an existing instance: '+name)
            names.add(name)
            uids.add(uid)
            clone = {'id': spec['id'], 'source': source, 'name': name, 'uniqueid': uid.hex(),
                     'world': list(spec['world']), 'fields': fields, 'asset': bool(asset)}
            plans[source['layer']]['clones'].append(clone)
            inserted.append({'name': name, 'uniqueid': uid.hex(), 'source': source['name'], 'layer': source['layer'],
                             'variants': source['variants'], 'asset': asset['family'] if asset else None})
        replacements, edits = {}, {}
        for uri, plan in plans.items():
            original = self.layers[uri]['doc']
            tree = Tree(original.data)
            if not tree.canonical:
                if plan['clones'] or plan['deletes'] or plan['retargets']:
                    raise ValueError('Layer layout is not canonical; only existing placement moves are supported: '+uri)
                # Non-canonical sources keep the copy-on-write scalar editor and its opaque bytes.
                for r, values in plan['moves']:
                    original.set(r['path'], values)
                replacements[uri], edits[uri] = original.to_bytes(), None
                continue
            for r, values in plan['moves']:
                tree.set_value(r['path'], values)
            for r, fields in plan['retargets']:
                for path, value in fields.items():
                    tree.set_value(('instances', r['index'])+path, value)
            for clone in plan['clones']:
                source = clone['source']
                tree.clone_entry(('instances',), source['index'], {('name',): clone['name'],
                    ('uniqueid',): clone['uniqueid'], ('overrides', 'WorldObject', 'transform'): clone['world'], **clone['fields']})
            # Remove last so earlier indices stay valid; clones of deleted sources were copied first.
            instances = tree.node(('instances',))
            for r in sorted(plan['deletes'], key=lambda r: r['index'], reverse=True):
                del instances.items[r['index']]
            data = tree.to_bytes()
            self._verify_layer(uri, data, plan)
            edits[uri] = self._patch_edits(uri, data, plan)
            replacements[uri] = data
        self.layer_edits, self.inserted, self.deleted = edits, inserted, deleted
        self.asset_resources = [(name, source, fragments) for name, (source, fragments) in sorted(assets.items())]
        self.asset_layers = {uri for uri, plan in plans.items() if plan['retargets'] or any(c.get('asset') for c in plan['clones'])}
        return replacements

    def _race_clones(self, specs, names, uids):
        """Number new race placements contiguously in every world that loads their layer."""
        existing = defaultdict(dict)  # (kind, number) -> {layer: uniqueid hex}
        for r in self.records:
            match = RACE_NAME.fullmatch(r['name'])
            if match:
                uid = self.layers[r['layer']]['doc'].leaves.get(('instances', r['index'], 'uniqueid'))
                existing[match.group(2), int(match.group(3))][r['layer']] = uid.raw.hex() if uid else None
        def kind_of(spec):
            source = self.by_id.get(spec['source'])
            if source is None:
                raise ValueError('Race placement source is no longer in the native track')
            if source['race_reason']:
                raise ValueError(f"{source['name']}: {source['race_reason']}")
            return RACE_NAME.fullmatch(source['name']).group(2), source
        ordered = sorted(specs, key=lambda s: (RACE_KINDS.index(kind_of(s)[0]), s.get('order', 0), s['id']))
        clones = []
        for spec in ordered:
            kind, source = kind_of(spec)
            layer, worlds = source['layer'], set(source['variants'])
            if not worlds:
                raise ValueError('Race placement layer is not loaded by any world: '+layer)
            # Variant worlds load together with the common world (stock variants omit base garages).
            variants_only = set(self.worlds) - {'common'}
            if 'common' in worlds:
                worlds = variants_only or {'common'}
            loaded = lambda other, world: world in self.layer_variants[other] or 'common' in self.layer_variants[other]
            visible = lambda other: all(loaded(other, w) for w in worlds)
            def numbers(world):
                return {n for (k, n), layers in existing.items() if k == kind and any(loaded(l, world) for l in layers)}
            per_world = {w: numbers(w) for w in worlds}
            number = max(max(ns, default=0) for ns in per_world.values()) + 1
            gaps = sorted(w for w, ns in per_world.items() if ns != set(range(1, number)))
            if gaps:
                raise ValueError(f'{kind}{number} would leave a numbering gap in {", ".join(gaps)}; '
                                 'add it to the variant-specific layer that holds the highest number')
            prefix = RACE_NAME.fullmatch(source['name']).group(1) or ''
            name = prefix + kind + str(number)
            uid = hashlib.md5(f"alterego-track-editor:{self.code}:{layer}:{name}".encode()).digest()
            if name in names or uid in uids:
                raise ValueError('New race placement identity collides with an existing instance: '+name)
            names.add(name)
            uids.add(uid)
            if kind == 'F1Garage':
                cars = []
                for n in (2 * number - 1, 2 * number):
                    found = [u for l, u in existing.get(('PitGarage', n), {}).items() if visible(l)]
                    if len(found) != 1:
                        raise ValueError(f'F1Garage{number} needs exactly one PitGarage{n} loaded wherever the garage is')
                    cars.append(found[0])
                fields = {('overrides', 'F1Garage', 'id'): number, ('overrides', 'F1Garage', 'left car placement'): cars[0],
                          ('overrides', 'F1Garage', 'right car placement'): cars[1]}
            else:
                fields = {('overrides', 'VehPlacement', 'Id'): number}
            existing[kind, number][layer] = uid.hex()
            clones.append({'id': spec['id'], 'source': source, 'name': name, 'uniqueid': uid.hex(),
                           'world': list(spec['world']), 'fields': fields, 'asset': False})
        return clones

    def pvs_names(self):
        """Instance names listed in precomputed-visibility object tables (NUL-terminated strings)."""
        if self._pvs_names is None:
            tables = [self.catalog.read(uri) for uri, (_, res) in self.catalog.by_uri.items() if res.type_name == 'PVSObjIDRes']
            self._pvs_names = {name for name in self.names if any(name.encode()+b'\0' in raw for raw in tables)}
        return self._pvs_names

    def deletion_reason(self, record, allow_pvs=False):
        if record['clone_reason'] or record['render_error']:
            return 'only static props can be deleted'
        if self._references is None:
            # String/woid values outside each entry's own name and uniqueid, across every loaded layer.
            strings, woids = set(), set()
            for info in self.layers.values():
                for path, leaf in info['doc'].leaves.items():
                    if len(path) >= 3 and path[0] == 'instances' and path[2] in ('name', 'uniqueid'):
                        continue
                    if leaf.type == 'stri':
                        strings.add(leaf.value)
                    elif leaf.type == 'woid':
                        woids.add(leaf.raw)
            self._references = strings, woids
        uid = self.layers[record['layer']]['doc'].leaves[('instances', record['index'], 'uniqueid')].raw
        if record['name'] in self._references[0] or uid in self._references[1]:
            return 'other placements reference it (for example a lightmap bake source)'
        if not allow_pvs and record['name'] in self.pvs_names():
            return 'it is listed in precomputed visibility data; enable the explicit PVS deletion option to proceed'
        return None

    def _asset_fields(self, asset, assets):
        """Validate one compiled independent family and merge its resources by exact identity."""
        model, binding = asset['family']+'?context=render', asset['binding']
        if not model.startswith('eaid://') or not binding.startswith('eaid://') or max(len(model.encode()), len(binding.encode())) > 255:
            raise ValueError('Asset model/binding references must be eaid strings of at most 255 bytes')
        names = {name for name, _, _ in asset['resources']}
        if asset['family']+'?render' not in names or asset['family']+'?model' not in names or binding not in names:
            raise ValueError('Incomplete independent geometry resources: '+asset['family'])
        for name, source, fragments in asset['resources']:
            if name in self.catalog.by_uri:
                raise ValueError('Asset resource already exists in the track: '+name)
            if name in assets and (assets[name][0].kind != source.kind or assets[name][1] != list(fragments)):
                raise ValueError('Two placed assets disagree on resource '+name)
            assets[name] = (source, list(fragments))
        return {('overrides', 'Model', 'model'): model, ('overrides', 'Model', 'mat binding'): binding}

    def _verify_layer(self, uri, data, plan):
        # Independent readback through the copy-on-write parser, not the tree writer.
        before = plain(self.layers[uri]['doc'].root)['instances']
        after = plain(Document(data).root)['instances']
        expected = copy.deepcopy(before)
        for r, values in plan['moves']:
            expected[r['index']]['overrides']['WorldObject']['transform'] = float32(values)
        for r, fields in plan['retargets']:
            for path, value in fields.items():
                expected[r['index']][path[0]][path[1]][path[2]] = value
        for clone in plan['clones']:
            item = copy.deepcopy(expected[clone['source']['index']])
            item.update(name=clone['name'], uniqueid=clone['uniqueid'])
            item['overrides']['WorldObject']['transform'] = float32(clone['world'])
            for path, value in clone['fields'].items():
                item['overrides'][path[1]][path[2]] = value
            expected.append(item)
        removed = {r['index'] for r in plan['deletes']}
        expected = [item for index, item in enumerate(expected) if index not in removed]
        if len(after) != len(expected):
            raise ValueError('Placement count readback failed: '+uri)
        for want, got in zip(expected, after):
            if want != got:
                raise ValueError('Placement readback failed: '+str(want.get('name', '')))

    def _patch_edits(self, uri, data, plan):
        """Launcher clone-entry/set-value edits, replayed offline to the exact full-export bytes."""
        names = [i.get('name') for i in plain(self.layers[uri]['doc'].root)['instances']]
        if plan['deletes'] or len(set(names)) != len(names):
            return None  # The launcher has no entry-removal edit; deletions need whole layers.
        if any(']' in r['name'] for r, _ in plan['moves']+plan['retargets']):
            return None
        edits = [{'op': 'set-value', 'path': f"instances[name={r['name']}].overrides.WorldObject.transform",
                  'value': float32(values)} for r, values in plan['moves']]
        edits += [{'op': 'set-value', 'path': f"instances[name={r['name']}]."+'.'.join(path), 'value': value}
                  for r, fields in plan['retargets'] for path, value in fields.items()]
        edits += [{'op': 'clone-entry', 'at': 'instances', 'src': f"[name={c['source']['name']}]", 'as': c['name'],
                   'set': {'uniqueid': c['uniqueid'], 'overrides.WorldObject.transform': float32(c['world']),
                           **{'.'.join(path): value for path, value in c['fields'].items()}}}
                  for c in plan['clones']]
        if patch_edits(Tree(self.layers[uri]['doc'].data), json.loads(json.dumps(edits))).to_bytes() != data:
            raise ValueError('Composable layer edit replay does not match the native output: '+uri)
        return edits

    def _locations(self, replacements):
        archives, loose = defaultdict(dict), {}
        for uri, data in replacements.items():
            if (uri, 0) in self.catalog.fragments:
                file, _ = self.catalog.fragments[uri, 0]
                if not file.is_relative_to(self.root):
                    raise ValueError('Edit targets an external addon dependency')
                loose[file.relative_to(self.root)] = data
                continue
            archive, _ = self.catalog.get(uri)
            if not archive.path.is_relative_to(self.root):
                raise ValueError('Edit targets a base dependency; export a separate update instead')
            original=self.catalog.read(uri,0)
            for candidate in self.catalog.archives:
                if not candidate.path.is_relative_to(self.root):
                    continue
                matches=[r for r in candidate.resources if r.name==uri]
                if not matches:continue
                if len(matches)!=1 or candidate.fragment_data(matches[0],0)!=original:
                    raise ValueError('Conflicting copies of the edited layer require explicit resolution: '+uri)
                archives[candidate.path.relative_to(self.root)][uri]=data
        return archives, loose

    def _loose_uris(self, replacements):
        return [uri for uri in replacements if (uri, 0) in self.catalog.fragments]

    def write_updated(self, output, replacements, asset_resources=None):
        output = Path(output).expanduser().resolve()
        if any((p/'F1_25.exe').is_file() for p in (output, *output.parents)):
            raise ValueError('Choose an output outside the game installation')
        if output.exists() or output.is_relative_to(self.source) or self.source.is_relative_to(output):
            raise ValueError('Choose a new destination outside the source tree')
        if self.is_addon and output.suffix.lower() not in ('.zip', '.swoftyaddon'):
            raise ValueError('Choose a new .swoftyaddon or .zip output')
        if not self.is_addon and output.suffix:
            raise ValueError('Choose a new track folder, not an archive filename')
        archives, loose = self._locations(replacements)
        if asset_resources is None:
            # Planned new-asset placements: embed families only beside the layers that use them.
            asset_resources, asset_layers = self.asset_resources, self.asset_layers
        else:
            asset_layers = set(replacements)
        if asset_resources and (not archives or any(uri in asset_layers for uri in self._loose_uris(replacements))):
            raise ValueError('Geometry integration requires archived native layers')
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.ate-update-', dir=output.parent) as temporary:
            stage = Path(temporary)/'track'
            stage.mkdir()
            for file in self.root.rglob('*'):
                if file.is_symlink():
                    raise ValueError('Symlinked source files require explicit resolution')
                if not file.is_file():
                    continue
                rel = file.relative_to(self.root)
                target = stage/rel
                target.parent.mkdir(parents=True, exist_ok=True)
                if rel in loose:
                    target.write_bytes(loose[rel])
                elif rel not in archives:
                    shutil.copyfile(file, target)
            for rel, resources in archives.items():
                original = next(a for a in self.catalog.archives if a.path == self.root/rel)
                from .native.formats.erp import Erp
                archive = Erp(original.path)
                for uri, data in resources.items():
                    archive.replace_fragment(uri, 0, data)
                embed = asset_resources if asset_layers & set(resources) else []
                if embed:
                    from .native.formats.erp import Resource,Fragment,STORED
                    for name,source,fragments in embed:
                        existing=[r for r in archive.resources if r.name==name]
                        if existing:
                            if len(existing)!=1 or existing[0].kind!=source.kind or len(existing[0].fragments)!=len(fragments) or any(archive.fragment_data(existing[0],i)!=raw for i,raw in enumerate(fragments)):
                                raise ValueError('Conflicting geometry dependency resource: '+name)
                            continue
                        added=[Fragment(f.name,0,len(raw),f.flags,STORED,len(raw),raw) for f,raw in zip(source.fragments,fragments)]
                        archive.resources.append(Resource(name,source.kind,source.unknown,added,b'\0'*16))
                archive.write(stage/rel)
                check = Erp(stage/rel)
                for uri, data in resources.items():
                    if check.fragment_data(uri, 0) != data:
                        raise ValueError('Native update readback failed')
                for name,_,fragments in embed:
                    for index,raw in enumerate(fragments):
                        if check.fragment_data(name,index)!=raw:raise ValueError('Integrated geometry resource readback failed')
            for a in self.catalog.archives:
                a._unchanged_source()
            if self.is_addon:
                packed=Path(temporary)/'updated.zip'
                with packed.open('xb') as stream:
                    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
                        for file in stage.rglob('*'):
                            if file.is_file():
                                archive.write(file, file.relative_to(stage).as_posix())
                with zipfile.ZipFile(packed) as check:
                    if check.testzip() is not None:
                        raise ValueError('Updated package ZIP validation failed')
                packed.rename(output)
            else:
                # New destination only; never overwrite a source or previous export.
                stage.rename(output)
        inserted = [i for i in self.inserted if i['layer'] in replacements]
        return {'changed_layers': len(replacements), 'game_verified': False, 'inserted_placements': inserted,
                'deleted_placements': [d for d in self.deleted if d['layer'] in replacements],
                'scope': 'Native WorldObject placement edits and explicit static-prop duplicates; other systems preserved',
                'limitations': INSERT_LIMITS if inserted else ''}

    def write_asset_update(self,identity,family,binding,resources,output):
        if self.is_addon:raise ValueError('Native geometry integration currently requires a track folder; addon archive targeting is unfinished')
        record=self.by_id[identity]
        if not record['model'] or record['render_error']:raise ValueError('Select a resolved native static model')
        doc=self.layers[record['layer']]['doc'];base=('instances',record['index'],'overrides','Model')
        paths=[base+('model',),base+('mat binding',)]
        if any(p not in doc.leaves or doc.leaves[p].type!='stri' for p in paths):raise ValueError('Native model/binding fields must already exist')
        names={name for name,_,_ in resources}
        if family+'?model' not in names or family+'?render' not in names or binding not in names:
            raise ValueError('Incomplete independent geometry resources')
        doc.set(paths[0],family+'?context=render');doc.set(paths[1],binding)
        result=self.write_updated(output,{record['layer']:doc.to_bytes()},resources)
        result['scope']='Existing static model retargeted to independent geometry; collision and race data preserved'
        result['collision_generated']=False
        return result

    def write_patch(self, output, replacements, edit_format='replace'):
        """Changes-only Swofty addon: whole-layer 'replace' or composable launcher 'patch-pkg' edits."""
        if edit_format not in ('replace', 'patch-pkg'):
            raise ValueError('Unknown layer edit format')
        if edit_format == 'patch-pkg':
            unavailable = [uri for uri in replacements if not self.layer_edits.get(uri)]
            if unavailable:
                raise ValueError('Composable edits need canonical layers with unique names and no deletions; use Whole Layers: '+unavailable[0])
        if self.is_addon:
            raise ValueError('Addon updates currently require complete updated-package export; changes-only targets need launcher archive resolution')
        output=Path(output).expanduser().resolve()
        if output.exists() or output.suffix.lower() not in ('.zip','.swoftyaddon'):
            raise ValueError('Choose a new .swoftyaddon or .zip filename')
        if output.is_relative_to(self.root) or any((p/'F1_25.exe').is_file() for p in (output,*output.parents)):
            raise ValueError('Export outside the source/game folder')
        archives,loose=self._locations(replacements)
        if loose or not replacements:
            raise ValueError('No supported changed native layers to package')
        output.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.ate-patch-',dir=output.parent) as temporary:
            stage=Path(temporary)/'patch.zip'
            ops=[];items=[];asset_archive='assets/new-assets.erp'
            with zipfile.ZipFile(stage,'w',zipfile.ZIP_DEFLATED) as z:
                if self.asset_resources:
                    from .static_asset import archive_bytes
                    from .native.storage import Catalog
                    header=self.catalog.get(sorted(self.asset_layers)[0])[0].header
                    payload=archive_bytes(self.asset_resources,header)
                    check_file=Path(temporary)/'new-assets.erp';check_file.write_bytes(payload)
                    check=Catalog();check.mount(check_file)
                    if any(check.read(name,i)!=raw for name,_,fragments in self.asset_resources for i,raw in enumerate(fragments)):
                        raise ValueError('New asset archive readback failed')
                    z.writestr(asset_archive,payload)
                for rel,resources in archives.items():
                    target='2025_asset_groups/environment_package/tracks/'+self.code+'/'+rel.as_posix()
                    if self.asset_layers & set(resources):
                        # copy-resource adds byte-exact families and fails rather than replacing an existing name.
                        for name,_,_ in self.asset_resources:
                            ops.append({'op':'copy-resource','source':asset_archive,'erp':target,'resource':name})
                    for uri,data in resources.items():
                        if edit_format=='patch-pkg':
                            # Launcher composes edits inside a resource with other addons instead of replacing it.
                            ops.append({'op':'patch-pkg','erp':target,'resource':uri,'fragment':0,'edits':self.layer_edits[uri]})
                        else:
                            name=f'fragments/{len(items):04d}.bin'
                            z.writestr(name,data)
                            ops.append({'op':'replace-resource','erp':target,'resource':uri,'fragment':0,'source':name})
                        items.append({'erp':target,'resource':uri,'sha256':digest(data)})
                manifest={'schema_version':1,'id':'local.alterego-track-update-'+self.code,
                    'name':self.code+' placement update','version':'0.2.0','author':'Local author',
                    'kind':['erp'],'category':'tracks','compat':{'game':'f1_25','launcher':'>=1.3.0'},
                    'operations':{'erp':['operations/erp.json']}}
                z.writestr('swofty.json',json.dumps(manifest,indent=2))
                z.writestr('operations/erp.json',json.dumps({'schema_version':1,'ops':ops},indent=2))
                inserted=[i for i in self.inserted if i['layer'] in replacements]
                z.writestr('provenance.json',json.dumps({'track_code':self.code,'game_verified':False,
                    'edit_format':edit_format,'changed_layers':items,'inserted_placements':inserted,
                    'deleted_placements':[d for d in self.deleted if d['layer'] in replacements],
                    'new_asset_resources':[name for name,_,_ in self.asset_resources],
                    'asset_dependencies':'Native material/shader/texture dependencies stay those of the source family',
                    'source_layers':{k:v['hash'] for k,v in self.layers.items()},
                    'scope':'Placement matrices and explicit static-prop duplicates; geometry/collision/AI regeneration not included',
                    'limitations':INSERT_LIMITS if inserted else '',
                    'sha256_meaning':'Expected layer bytes after these edits on the recorded source layers'},indent=2))
            with zipfile.ZipFile(stage) as z:
                if z.testzip() is not None:raise ValueError('Patch archive validation failed')
            stage.rename(output)
        return len(ops)

    def close(self):
        if self.addon_scene:
            for temporary in self.addon_scene._addon_temp:
                if temporary:
                    temporary.cleanup()
            self.addon_scene = None
        if self.package_temporary:
            self.package_temporary.cleanup()
            self.package_temporary = None
