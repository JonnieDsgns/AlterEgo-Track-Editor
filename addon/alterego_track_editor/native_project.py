"""Native track graph with stable layer provenance and copy-preserving updates.

Uses the bundled TrackView codecs. No engine/runtime code or installation API.
"""
from collections import defaultdict
import copy
import hashlib
import json
from pathlib import Path
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

    def insert_name(self, source, identity):
        name = f"{source['name']}_ate_{identity[:12]}"
        if len(name.encode('utf-8')) > 255:
            raise ValueError('Generated placement name exceeds 255 bytes: '+source['name'])
        return name

    def apply(self, changes, insertions=()):
        """Plan existing matrix edits and explicit new placements; returns changed layer bytes.

        insertions: [{'id': stable new identity, 'source': record id, 'world': 16 floats}].
        """
        plans = defaultdict(lambda: {'moves': [], 'clones': []})
        for identity, values in changes.items():
            r = self.by_id[identity]
            if not r['editable']:
                raise ValueError('Placement has no supported native WorldObject matrix: '+r['name'])
            if r['render_error']:
                raise ValueError('Cannot edit unresolved render placement: '+r['name'])
            plans[r['layer']]['moves'].append((r, list(values)))
        names, uids, inserted = set(self.names), set(self.unique_ids), []
        for spec in sorted(insertions, key=lambda s: s['id']):
            source = self.by_id.get(spec['source'])
            if source is None:
                raise ValueError('Duplicated placement source is no longer in the native track')
            if source['clone_reason'] or source['render_error']:
                raise ValueError(f"{source['name']}: {source['clone_reason'] or source['render_error']}")
            name = self.insert_name(source, spec['id'])
            uid = hashlib.md5(f"alterego-track-editor:{self.code}:{source['layer']}:{name}".encode()).digest()
            if name in names or uid in uids:
                raise ValueError('New placement identity collides with an existing instance: '+name)
            names.add(name)
            uids.add(uid)
            clone = {'id': spec['id'], 'source': source, 'name': name, 'uniqueid': uid.hex(), 'world': list(spec['world'])}
            plans[source['layer']]['clones'].append(clone)
            inserted.append({'name': name, 'uniqueid': uid.hex(), 'source': source['name'], 'layer': source['layer'],
                             'variants': source['variants']})
        replacements, edits = {}, {}
        for uri, plan in plans.items():
            original = self.layers[uri]['doc']
            tree = Tree(original.data)
            if not tree.canonical:
                if plan['clones']:
                    raise ValueError('Layer layout is not canonical; new placements are refused: '+uri)
                # Non-canonical sources keep the copy-on-write scalar editor and its opaque bytes.
                for r, values in plan['moves']:
                    original.set(r['path'], values)
                replacements[uri], edits[uri] = original.to_bytes(), None
                continue
            for r, values in plan['moves']:
                tree.set_value(r['path'], values)
            for clone in plan['clones']:
                source = clone['source']
                tree.clone_entry(('instances',), source['index'], {('name',): clone['name'],
                    ('uniqueid',): clone['uniqueid'], ('overrides', 'WorldObject', 'transform'): clone['world']})
            data = tree.to_bytes()
            self._verify_layer(uri, data, plan)
            edits[uri] = self._patch_edits(uri, data, plan)
            replacements[uri] = data
        self.layer_edits, self.inserted = edits, inserted
        return replacements

    def _verify_layer(self, uri, data, plan):
        # Independent readback through the copy-on-write parser, not the tree writer.
        before = plain(self.layers[uri]['doc'].root)['instances']
        after = plain(Document(data).root)['instances']
        moved = {r['index']: float32(values) for r, values in plan['moves']}
        if len(after) != len(before) + len(plan['clones']):
            raise ValueError('Inserted placement count readback failed: '+uri)
        for index, item in enumerate(before):
            expected = copy.deepcopy(item)
            if index in moved:
                expected['overrides']['WorldObject']['transform'] = moved[index]
            if after[index] != expected:
                raise ValueError('Existing placement changed unexpectedly: '+item.get('name', ''))
        for clone, item in zip(plan['clones'], after[len(before):]):
            expected = copy.deepcopy(before[clone["source"]["index"]])
            expected.update(name=clone['name'], uniqueid=clone['uniqueid'])
            expected['overrides']['WorldObject']['transform'] = float32(clone['world'])
            if item != expected:
                raise ValueError('New placement readback failed: '+clone['name'])

    def _patch_edits(self, uri, data, plan):
        """Launcher clone-entry/set-value edits, replayed offline to the exact full-export bytes."""
        names = [i.get('name') for i in plain(self.layers[uri]['doc'].root)['instances']]
        if len(set(names)) != len(names):
            return None
        edits = [{'op': 'set-value', 'path': f"instances[name={r['name']}].overrides.WorldObject.transform",
                  'value': float32(values)} for r, values in plan['moves'] if ']' not in r['name']]
        if len(edits) != len(plan['moves']):
            return None
        edits += [{'op': 'clone-entry', 'at': 'instances', 'src': f"[name={c['source']['name']}]", 'as': c['name'],
                   'set': {'uniqueid': c['uniqueid'], 'overrides.WorldObject.transform': float32(c['world'])}}
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
        if asset_resources and (loose or not archives):raise ValueError('Geometry integration requires archived native layers')
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
                if asset_resources:
                    from .native.formats.erp import Resource,Fragment,STORED
                    for name,source,fragments in asset_resources:
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
                for name,_,fragments in asset_resources or []:
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
                raise ValueError('Composable edits need canonical layers with unique names; use whole-layer replacement: '+unavailable[0])
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
            ops=[];items=[]
            with zipfile.ZipFile(stage,'w',zipfile.ZIP_DEFLATED) as z:
                for rel,resources in archives.items():
                    target='2025_asset_groups/environment_package/tracks/'+self.code+'/'+rel.as_posix()
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
