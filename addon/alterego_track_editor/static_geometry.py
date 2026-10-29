"""Conservative static topology compiler, derived from the owned Tracktool contract.

Single-submesh, single-LOD templates only. Produces fragment replacements, never
world/collision edits. Native material bindings and opaque descriptor bytes remain.
See docs/research/static-writer.md for evidence and limits.
"""
from dataclasses import dataclass
import math
from pathlib import Path
import struct
import tempfile
from .native.geometry import u32, region, pool, mesh, buffer
from .native.scene import render_transform, transformed_bounds
from .native.storage import Catalog
from .native.formats.erp import Erp


@dataclass
class StaticInput:
    positions: list
    indices: list
    # Native vertex attributes keyed by (semantic, channel). Normal has 3 lanes;
    # tangent and UV streams have 4; colour contains 4 bytes (not guessed defaults).
    attributes: dict


class StaticTemplate:
    def __init__(self, catalog, uri):
        if not uri.endswith('.idf?lod=0&mesh') or uri.count('&') != 1:
            raise ValueError('Choose a direct static LOD-0 mesh template')
        self.catalog, self.uri = catalog, uri
        self.family = uri[:-len('?lod=0&mesh')]
        self.data = catalog.read(uri)
        if u32(self.data, 0) != 1 or u32(self.data, 8) != 1:
            raise ValueError('This compiler currently requires one submesh and one index buffer')
        region(self.data, 76, 88)
        offsets = [76+u32(self.data, p) for p in (20,24,28,32,40,44)]
        if not (164 <= offsets[0] <= offsets[1] <= offsets[2] <= offsets[3] <= len(self.data)):
            raise ValueError('Invalid static descriptor pools')
        self.vb = pool(self.data, offsets[0], offsets[1], u32(self.data,4))
        self.ib = pool(self.data, offsets[1], offsets[2], 1)[0]
        count = u32(self.data,36)
        region(self.data, offsets[4], count*20)
        region(self.data, offsets[5], count*8)
        active = u32(self.data,76)
        if not 1 <= active <= 8:
            raise ValueError('Unsupported static declaration count')
        self.streams = {}
        for lane in range(active):
            index = u32(self.data,132+lane*4)
            if index >= count:
                raise ValueError('Invalid static declaration index')
            declaration = struct.unpack_from('<5I',self.data,offsets[4]+index*20)
            _, offset, semantic, channel, _ = declaration
            if offset or semantic not in (1,2,3,5,6) or (channel and (semantic,channel)!=(5,1)):
                raise ValueError('Unsupported static vertex layout')
            slot = u32(self.data,offsets[5]+index*8+4)
            if slot >= len(self.vb) or (semantic,channel) in self.streams:
                raise ValueError('Invalid or duplicated static stream binding')
            resource = self.vb[slot]
            if resource in self.streams.values():
                raise ValueError('Aliased static attribute streams are unsupported')
            stride, _, fmt, _ = buffer(catalog,resource)
            expected = (12,39) if semantic==1 else (4,14) if semantic==6 else (8,35)
            if (stride,fmt)!=expected or u32(catalog.read(resource),0)!=4361:
                raise ValueError('Unsupported static buffer encoding')
            self.streams[semantic,channel] = resource
        if (1,0) not in self.streams or set(self.vb)!=set(self.streams.values()) or self.ib in self.vb:
            raise ValueError('Missing position or unused/aliased template streams')
        index_stride, _, index_format, _ = buffer(catalog,self.ib)
        if (index_stride,index_format) != (2,19):
            raise ValueError('Static compiler requires a UInt16 index template')
        draws, self.draw = u32(self.data,56), 76+u32(self.data,60)
        region(self.data,self.draw,16*draws)
        if draws!=1 or u32(self.data,self.draw+4)!=0 or self.data[self.draw+8:self.draw+16]!=self.data[88:96]:
            raise ValueError('Template needs one complete draw for its submesh')
        self.model = catalog.read(self.family+'?model')
        if len(self.model)<72 or u32(self.model,0)!=1:
            raise ValueError('Template must be a single-LOD model')
        render = catalog.read(self.family+'?render')
        if len(render)<252:
            raise ValueError('Template needs a supported static render graph')
        self.transform = render_transform(catalog,self.family)
        if not all(map(math.isfinite,self.transform)):
            raise ValueError('Non-finite static render transform')
        m=self.transform
        determinant=m[0]*(m[5]*m[10]-m[9]*m[6])-m[4]*(m[1]*m[10]-m[9]*m[2])+m[8]*(m[1]*m[6]-m[5]*m[2])
        if abs(determinant)<1e-10:raise ValueError('Singular static render transform')
        owned = set(self.vb+[self.ib])
        for name in catalog.by_uri:
            if name==uri or not name.endswith('&mesh'):continue
            data=catalog.read(name)
            if any((s+'\0').encode() in data for s in owned):
                raise ValueError('Template buffers are shared with another mesh/LOD')
        # Validate every resource and existing geometry before considering edits.
        for name in owned|{uri,self.family+'?model',self.family+'?render'}:
            _,resource=catalog.get(name)
            if len(resource.fragments)!=(2 if name in owned else 1):
                raise ValueError('Unexpected static resource fragment layout')
        mesh(catalog,uri)

    def compile(self, source):
        count=len(source.positions)
        if not 3<=count<=65536 or not source.indices or len(source.indices)%3 or len(source.indices)>3_000_000:
            raise ValueError('Static geometry exceeds supported vertex/triangle limits')
        expected=set(self.streams)-{(1,0)}
        if set(source.attributes)!=expected:
            raise ValueError('Supply exactly the attributes required by the native template')
        if any(type(i) is not int or i<0 or i>=count for i in source.indices):
            raise ValueError('Triangle index outside authored positions')
        for i in range(0,len(source.indices),3):
            if len(set(source.indices[i:i+3]))!=3:
                raise ValueError('Degenerate triangle indices')
        result={}
        def encode(uri, values, lanes, code):
            if len(values)!=count or any(len(row)!=lanes or not all(math.isfinite(v) for v in row) for row in values):
                raise ValueError('Invalid authored vertex attribute values')
            if code=='B' and any(type(v) is not int or not 0<=v<=255 for row in values for v in row):
                raise ValueError('Native vertex colours must be bytes')
            try:payload=b''.join(struct.pack('<'+code*lanes,*row) for row in values)
            except (OverflowError,struct.error) as exc:raise ValueError('Vertex value exceeds native encoding') from exc
            header=bytearray(self.catalog.read(uri));struct.pack_into('<I',header,8,count)
            result[uri,0]=bytes(header);result[uri,1]=payload
        encode(self.streams[1,0],source.positions,3,'f')
        for key in expected:
            rows=source.attributes[key]
            if key==(2,0):
                if any(len(row)!=3 or abs(sum(v*v for v in row)-1)>0.02 for row in rows):
                    raise ValueError('Static normals must be normalized')
                rows=[(*row,0.) for row in rows]
            if key==(3,0):
                if any(len(row)!=4 or abs(sum(v*v for v in row[:3])-1)>0.02 or row[3] not in (-1.,1.) for row in rows):
                    raise ValueError('Static tangents need a unit direction and signed handedness')
            encode(self.streams[key],rows,4,'B' if key==(6,0) else 'e')
        header=bytearray(self.catalog.read(self.ib));struct.pack_into('<I',header,8,len(source.indices))
        result[self.ib,0]=bytes(header)
        result[self.ib,1]=struct.pack('<'+'H'*len(source.indices),*source.indices)
        # Calculate bounds using quantized positions, matching the emitted buffers.
        points=list(struct.iter_unpack('<3f',result[self.streams[1,0],1]))
        for i in range(0,len(source.indices),3):
            a,b,c=(points[j] for j in source.indices[i:i+3])
            ab=[b[k]-a[k] for k in range(3)];ac=[c[k]-a[k] for k in range(3)]
            cross=[ab[1]*ac[2]-ab[2]*ac[1],ab[2]*ac[0]-ab[0]*ac[2],ab[0]*ac[1]-ab[1]*ac[0]]
            if sum(v*v for v in cross)<=1e-20:raise ValueError('Triangle collapses at native float precision')
        bounds=[min(p[k] for p in points) for k in range(3)]+[max(p[k] for p in points) for k in range(3)]
        def sphere(bounds):
            center=[(bounds[k]+bounds[k+3])/2 for k in range(3)]
            return (*center, math.sqrt(sum((bounds[k+3]-center[k])**2 for k in range(3))))
        data=bytearray(self.data)
        struct.pack_into('<3I',data,88,0,len(source.indices),0)
        struct.pack_into('<4f',data,100,*sphere(bounds))
        struct.pack_into('<2I',data,self.draw+8,0,len(source.indices))
        result[self.uri,0]=bytes(data)
        model=bytearray(self.model);world=transformed_bounds(bounds,self.transform)
        struct.pack_into('<4f',model,16,*sphere(world))
        struct.pack_into('<3f',model,36,*world[:3]);struct.pack_into('<3f',model,48,*world[3:])
        result[self.family+'?model',0]=bytes(model)
        return result


def write_test(catalog, uri, source, destination):
    """Write an isolated full ERP copy for offline inspection; no track/package claim."""
    template=StaticTemplate(catalog,uri)
    replacements=template.compile(source)
    archive,_=catalog.get(uri)
    if any(catalog.get(name)[0] is not archive for name,_ in replacements):
        raise ValueError('Static template resources must belong to the same archive')
    destination=Path(destination).expanduser().resolve()
    if destination.suffix.lower()!='.erp':raise ValueError('Geometry test output must be an .erp file')
    if destination in {a.path.resolve() for a in catalog.archives}:raise ValueError('Choose an output outside the source')
    if any((p/'F1_25.exe').exists() for p in destination.parents):
        raise ValueError('Choose an output outside the game installation')
    if destination.exists():raise ValueError('Choose a new output path')
    destination.parent.mkdir(parents=True,exist_ok=True)
    # Use a fresh archive so failed compilation never contaminates the source catalog.
    copy=Erp(archive.path)
    for (name,fragment),payload in replacements.items():copy.replace_fragment(name,fragment,payload)
    with tempfile.TemporaryDirectory(prefix='ate-static-',dir=destination.parent) as folder:
        staged=Path(folder)/'geometry.erp';copy.write(staged)
        check=Catalog();check.mount(staged)
        decoded=mesh(check,uri)
        if decoded.triangles!=len(source.indices)//3:raise ValueError('Generated geometry readback failed')
        for (name,fragment),payload in replacements.items():
            if check.read(name,fragment)!=payload:raise ValueError('Generated fragment readback differs')
        # Exclusive creation avoids replacing a file created during validation.
        import shutil
        with destination.open('xb') as out:
            try:
                with staged.open('rb') as src:shutil.copyfileobj(src,out)
            except BaseException:
                out.close();destination.unlink(missing_ok=True)
                raise
    return {'vertices':len(source.positions),'triangles':decoded.triangles,'changed_fragments':len(replacements),
            'world_mounted':False,'collision_generated':False,'game_verified':False}
