"""Track assembly and model documents, independent of an editor or game runtime."""
import json
import math
from pathlib import Path
import struct
import threading
import hashlib
from collections import OrderedDict
from .storage import Catalog
from .formats.pkg import Document, Scalar
from .geometry import mesh, terrain_info, triangles, combine, u32, cstring, Geometry

IDENTITY = [1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.]


def plain(value):
    if isinstance(value, Scalar):
        return value.value
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v) for v in value]
    return value


def multiply(a, b):
    # Column-major arrays. Native row-vector matrices flatten to the same
    # byte order as their column-vector transpose in glTF/WebGL.
    return [sum(a[k*4+r]*b[c*4+k] for k in range(4)) for c in range(4) for r in range(4)]


def trs(t, q, s):
    x,y,z,w = q
    return [(1-2*y*y-2*z*z)*s[0], (2*x*y+2*z*w)*s[0], (2*x*z-2*y*w)*s[0], 0.,
            (2*x*y-2*z*w)*s[1], (1-2*x*x-2*z*z)*s[1], (2*y*z+2*x*w)*s[1], 0.,
            (2*x*z+2*y*w)*s[2], (2*y*z-2*x*w)*s[2], (1-2*x*x-2*y*y)*s[2], 0., *t, 1.]


def transformed_bounds(bounds, matrix):
    points = [[sum(matrix[k*4+r]*p[k] for k in range(3))+matrix[12+r] for r in range(3)]
              for p in ((x,y,z) for x in (bounds[0],bounds[3]) for y in (bounds[1],bounds[4]) for z in (bounds[2],bounds[5]))]
    return [min(p[k] for p in points) for k in range(3)]+[max(p[k] for p in points) for k in range(3)]


class Scene:
    def __init__(self):
        self.catalog = Catalog()
        self.instances = []
        self.specs = {}
        self.warnings = []
        self.geometry_cache = OrderedDict()
        self.geometry_used = 0
        self.geometry_budget = 96*1024*1024
        self.lock = threading.RLock()
        self.title = ''
        self.sources = []
        self.bounds = None
        self.unsupported = {}
        self.source_identities = {}
        from .materials import Materials
        self.materials=Materials(self.catalog)
        self.binding_variants={}

    def validate_sources(self):
        self.materials.validate_sources()
        for archive in self.catalog.archives:
            archive._unchanged_source()
        for path,identity in self.source_identities.items():
            stat = Path(path).stat()
            if (stat.st_size,stat.st_mtime_ns)!=identity:
                raise ValueError('Source changed; reopen it')

    def add(self, key, spec, name, matrix, bounds, layer='Models',binding=None):
        if len(matrix) != 16 or not all(map(math.isfinite, matrix)):
            raise ValueError('Invalid instance matrix')
        if any(abs(matrix[k]) > 1e-5 for k in (3,7,11)) or abs(matrix[15]-1) > 1e-5:
            raise ValueError('Non-affine instance matrix')
        self.specs.setdefault(key, spec)
        world = transformed_bounds(bounds, matrix)
        variant=hashlib.sha256((binding or '').encode()).hexdigest()[:16]
        self.binding_variants.setdefault(key,{})[variant]=binding
        self.instances.append(dict(key=key, name=name, matrix=matrix, bounds=world, layer=layer,appearance=variant))
        if self.bounds is None:
            self.bounds = world[:]
        else:
            self.bounds = [min(self.bounds[k],world[k]) for k in range(3)]+[max(self.bounds[k+3],world[k+3]) for k in range(3)]

    def metadata(self):
        core = [i['bounds'] for i in self.instances if i['layer']!='Terrain']
        framing = ([min(b[k] for b in core) for k in range(3)]+[max(b[k+3] for b in core) for k in range(3)]) if core else self.bounds
        return dict(title=self.title, instances=self.instances, bounds=self.bounds or [-1,-1,-1,1,1,1],
                    framingBounds=framing,
                    uniqueGeometry=len(self.specs), warnings=self.warnings,
                    stats=self.catalog.stats(), appearance='Textured material preview; game lighting and complex shaders approximated')

    def appearances(self,key,geometry=None):
        g=geometry or self.geometry(key)
        groups=g.groups or [dict(first=0,count=len(g.indices)//4,slot='Default')]
        return {variant:[group.get('appearance') or self.materials.resolve(binding,group.get('slot',''),group.get('material')) for group in groups]
                for variant,binding in self.binding_variants.get(key,{'':None}).items()}

    def geometry(self, key):
        with self.lock:
            self.validate_sources()
            if key in self.unsupported:
                raise ValueError(self.unsupported[key])
            if key in self.geometry_cache:
                self.geometry_cache.move_to_end(key)
                return self.geometry_cache[key]
            spec = self.specs[key]
            try:
                if spec[0] == 'mesh':
                    result = mesh(self.catalog, spec[1])
                elif spec[0] == 'terrain':
                    _, position, ib, draw, normal,attrs,material = spec
                    first, count, base, _ = draw
                    result = combine([triangles(self.catalog, position, ib, first, count, base, normal,attrs)])
                    from .terrain_materials import bake_terrain,surface_world_uvs
                    appearance=surface_world_uvs(result,self.materials.resolve(None,'',material))
                    try:appearance=bake_terrain(self.materials,result,appearance,key,lambda:self.geometry(key))
                    except Exception as exc:self.materials.note(key,exc)
                    result.groups=[dict(first=0,count=count,slot=material.rsplit('/',1)[-1],material=material,appearance=appearance)]
                else:
                    result = spec[1]()
            except Exception as exc:
                self.unsupported[key] = str(exc)
                raise
            size = len(result.positions)+len(result.normals)+len(result.indices)+len(result.colours)+sum(map(len,result.uvs))
            while self.geometry_cache and self.geometry_used+size > self.geometry_budget:
                _, old = self.geometry_cache.popitem(last=False)
                self.geometry_used -= len(old.positions)+len(old.normals)+len(old.indices)+len(old.colours)+sum(map(len,old.uvs))
            if size <= self.geometry_budget:
                self.geometry_cache[key] = result
                self.geometry_used += size
            return result


def render_transform(catalog, family):
    uri = family+'?render'
    if uri not in catalog.by_uri:
        raise ValueError('Render hierarchy missing')
    data = catalog.read(uri)
    n, links = struct.unpack_from('<HH', data)
    if links or n < 2 or 12+120*n > len(data):
        raise ValueError('Unsupported render hierarchy')
    nodes = []
    for i in range(n):
        p = 12+120*i
        parent = struct.unpack_from('<i', data, p+4)[0]
        kind = u32(data, p+112)
        if (i == 0 and parent != -1) or (i > 0 and (parent != 0 or kind != 1)):
            raise ValueError('Unsupported render attachments')
        values = struct.unpack_from('<10f', data, p+8)
        nodes.append(trs(values[:3],values[3:7],values[7:10]))
    if n > 2 and any(any(abs(a-b)>1e-5 for a,b in zip(m, IDENTITY)) for m in nodes):
        raise ValueError('Nonidentity multi-node placement is unresolved')
    return multiply(nodes[0], nodes[1])


def mesh_bounds(catalog, uri):
    data = catalog.read(uri)
    n = u32(data, 0)
    if n < 1 or 76+88*n > len(data):
        raise ValueError('Unsupported mesh bounds')
    boxes = []
    for i in range(n):
        x,y,z,r = struct.unpack_from('<4f', data, 76+88*i+24)
        if r < 0 or not all(map(math.isfinite, (x,y,z,r))):
            raise ValueError('Invalid mesh bounds')
        boxes.append([x-r,y-r,z-r,x+r,y+r,z+r])
    return [min(b[k] for b in boxes) for k in range(3)]+[max(b[k+3] for b in boxes) for k in range(3)]


def open_track(path, variant='f1', catalog=None):
    if variant not in ('f1','f1_26','f1_myteam','f1_26_myteam','f2','f2_26','classic'):
        raise ValueError('Unsupported track variant')
    folder = Path(path).expanduser().resolve()
    scene = Scene()
    if catalog is not None:
        scene.catalog=catalog
        scene.materials.catalog=catalog
    scene.title = folder.name+' / '+variant
    variant_path = folder/'wep'/f'{folder.name}_{variant}.erp'
    variant_world=f'eaid://environment_package/tracks/{folder.name}/wep/{folder.name}_{variant}.wep'
    if not variant_path.is_file() and variant_world not in scene.catalog.by_uri:
        raise ValueError('Selected track variant is not installed')
    for p in (variant_path,
              folder/'wep'/f'{folder.name}_common.erp', folder/f'{folder.name}_common.erp'):
        if p.is_file():
            scene.catalog.mount(p)
            scene.sources.append(str(p))
    scene.sources=list(dict.fromkeys(scene.sources+[str(a.path) for a in scene.catalog.archives]))
    if not scene.sources:
        raise ValueError('No track archives found in this folder')
    layers = set()
    for archive in scene.catalog.archives:
        for resource in archive.resources:
            if resource.type_name == 'World' and resource.name in (variant_world,variant_world.removesuffix('_'+variant+'.wep')+'_common.wep'):
                try:
                    root = plain(Document(scene.catalog.read(resource.name)).root)
                    layers.update(root.get('layers', []))
                except Exception as exc:
                    scene.warnings.append(dict(name=resource.name, reason=str(exc)))
    model_cache = {};terrain_references={}
    for uri in sorted(layers):
        try:
            doc = plain(Document(scene.catalog.read(uri)).root)
        except Exception as exc:
            scene.warnings.append(dict(name=uri, reason=str(exc)))
            continue
        for instance in doc.get('instances', []):
            name = instance.get('name', 'Unnamed')
            terrain_model=instance.get('overrides',{}).get('TerrainModel',{}).get('model')
            if terrain_model:
                terrain_references[terrain_model]=instance.get('overrides',{}).get('WorldObject',{}).get('transform',IDENTITY[:])
            try:
                if instance.get('template') != 'RenderModel':
                    raise ValueError('Unsupported class: '+str(instance.get('template')))
                overrides = instance.get('overrides', {})
                model = overrides.get('Model', {}).get('model', '')
                suffix = '?context=render'
                if not model.endswith(suffix):
                    raise ValueError('Missing explicit render model reference')
                family = model[:-len(suffix)]
                mesh_uri = family+'?lod=0&mesh'
                if mesh_uri not in model_cache:
                    model_cache[mesh_uri] = (render_transform(scene.catalog, family), mesh_bounds(scene.catalog, mesh_uri))
                render, bounds = model_cache[mesh_uri]
                matrix = overrides.get('WorldObject', {}).get('transform')
                if matrix is None and '.sponsor_' in family and '/tracks/'+folder.name+'/' in family:
                    # Track-local sponsor chunks carry their placement in the
                    # two-node render hierarchy instead of a WorldObject override.
                    matrix=IDENTITY[:]
                if not isinstance(matrix, list):
                    raise ValueError('Missing explicit world placement')
                scene.add(mesh_uri, ('mesh',mesh_uri), name, multiply(matrix,render), bounds, uri.rsplit('/',1)[-1],overrides.get('Model',{}).get('mat binding'))
            except Exception as exc:
                scene.warnings.append(dict(name=name, layer=uri, reason=str(exc)))
    for uri, (_, res) in list(scene.catalog.by_uri.items()):
        if res.type_name != 'TerrainRes' or not uri.endswith('?context=render'):
            continue
        if uri not in terrain_references:continue
        try:
            data = scene.catalog.read(uri)
            for cell,j,position,ib,draw,normal,attrs,material in terrain_info(data):
                p = 16+48*cell
                low = struct.unpack_from('<3f', data, p+16)
                high = struct.unpack_from('<3f', data, p+32)
                key = f'{uri}#{cell}:{j}'
                scene.add(key, ('terrain',position,ib,draw,normal,attrs,material), f'Terrain {cell} / {j}', terrain_references[uri], list(low+high), 'Terrain')
        except Exception as exc:
            scene.warnings.append(dict(name=uri, reason=str(exc)))
    if not scene.instances:
        raise ValueError('No supported placed geometry found')
    return scene


def open_erp(path):
    scene = Scene()
    scene.title = Path(path).name
    scene.catalog.mount(path)
    scene.sources = [str(Path(path).resolve())]
    for uri, (_, res) in scene.catalog.by_uri.items():
        if res.type_name == 'GfxMeshRes' and '?lod=0&mesh' in uri:
            try:
                family=uri.split('?')[0]
                binding=family.removesuffix('.idf')+'.emb?context=default'
                scene.add(uri, ('mesh',uri), uri.rsplit('/',1)[-1], IDENTITY[:], mesh_bounds(scene.catalog, uri),binding=binding)
            except Exception as exc:
                scene.warnings.append(dict(name=uri,reason=str(exc)))
    if not scene.instances:
        raise ValueError('No supported LOD 0 meshes in archive')
    scene.warnings.append(dict(name='Archive view',reason='Meshes shown in local coordinates; use Open track for placed scenes.'))
    return scene
