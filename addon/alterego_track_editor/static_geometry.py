"""Conservative static topology compiler, derived from the owned Tracktool contract.

Complete static LOD families and material submeshes. Produces fragments, never
world/collision edits. Native material bindings and opaque descriptor bytes remain.
See docs/research/static-writer.md for evidence and limits.
"""
from dataclasses import dataclass
import math
from pathlib import Path
import struct
import tempfile
from .native.geometry import u32, region, pool, mesh, buffer,cstring
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
    def __init__(self, catalog, uri, family_uris=None):
        import re
        match=re.fullmatch(r'(.+\.idf)\?lod=(0|[1-9][0-9]*)&mesh',uri)
        if not match or (family_uris is None and match[2]!='0'):
            raise ValueError('Choose a direct static LOD-0 mesh template')
        self.catalog,self.uri,self.family=catalog,uri,match[1]
        self.data=catalog.read(uri)
        n=u32(self.data,0)
        if not 1<=n<=10000 or u32(self.data,8)!=1:
            raise ValueError('Static compiler needs populated submeshes and one index buffer')
        region(self.data,76,88*n)
        offsets=[76+u32(self.data,p) for p in (20,24,28,32,40,44)]
        if not (76+88*n<=offsets[0]<=offsets[1]<=offsets[2]<=offsets[3]<=len(self.data)):
            raise ValueError('Invalid static descriptor pools')
        self.vb=pool(self.data,offsets[0],offsets[1],u32(self.data,4))
        self.ib=pool(self.data,offsets[1],offsets[2],1)[0]
        count=u32(self.data,36)
        region(self.data,offsets[4],count*20);region(self.data,offsets[5],count*8)
        self.parts=[];self.slots=[];owners={}
        for part in range(n):
            record=76+88*part;active=u32(self.data,record)
            if not 1<=active<=8:raise ValueError('Unsupported static declaration count')
            streams={}
            for lane in range(active):
                index=u32(self.data,record+56+lane*4)
                if index>=count:raise ValueError('Invalid static declaration index')
                _,offset,semantic,channel,_=struct.unpack_from('<5I',self.data,offsets[4]+20*index)
                if offset or semantic not in (1,2,3,5,6) or (channel and (semantic,channel)!=(5,1)):
                    raise ValueError('Unsupported static vertex layout')
                slot=u32(self.data,offsets[5]+8*index+4)
                if slot>=len(self.vb) or (semantic,channel) in streams:
                    raise ValueError('Invalid or duplicated static stream binding')
                resource=self.vb[slot]
                if resource in streams.values():raise ValueError('Aliased static attribute streams are unsupported')
                stride,_,fmt,_=buffer(catalog,resource)
                expected=(12,39) if semantic==1 else (4,14) if semantic==6 else (8,35)
                if (stride,fmt)!=expected or u32(catalog.read(resource),0)!=4361:
                    raise ValueError('Unsupported static buffer encoding')
                streams[semantic,channel]=resource
            if (1,0) not in streams:raise ValueError('Position stream missing')
            for key,resource in streams.items():
                owner=(streams[1,0],key)
                if resource in owners and owners[resource]!=owner:
                    raise ValueError('Incompatible shared attribute stream ownership')
                owners[resource]=owner
            self.parts.append(streams)
            self.slots.append(cstring(self.data,offsets[2]+u32(self.data,record+48),offsets[3]))
        self.streams=self.parts[0] # Compatibility with the single-primitive adapter.
        if set(self.vb)!=set(owners) or self.ib in owners:
            raise ValueError('Unused or aliased template streams')
        stride,_,fmt,_=buffer(catalog,self.ib)
        if (stride,fmt)!=(2,19):raise ValueError('Static compiler requires a UInt16 index template')
        draws,draw=u32(self.data,56),76+u32(self.data,60)
        region(self.data,draw,16*draws)
        if draws!=n:raise ValueError('Template needs one complete draw per submesh')
        self.draws={}
        for i in range(draws):
            p=draw+i*16;part=u32(self.data,p+4)
            if part>=n or part in self.draws or self.data[p+8:p+16]!=self.data[88+part*88:96+part*88]:
                raise ValueError('Template needs one complete draw per submesh')
            self.draws[part]=p
        self.model=catalog.read(self.family+'?model')
        lods=u32(self.model,0)
        self.lod_count=lods
        if not 1<=lods<=128 or len(self.model)<64+8*lods or (family_uris is None and lods!=1):
            raise ValueError('Template requires a complete LOD family')
        self.transform=render_transform(catalog,self.family)
        if not all(map(math.isfinite,self.transform)):raise ValueError('Non-finite static render transform')
        m=self.transform
        determinant=m[0]*(m[5]*m[10]-m[9]*m[6])-m[4]*(m[1]*m[10]-m[9]*m[2])+m[8]*(m[1]*m[6]-m[5]*m[2])
        if abs(determinant)<1e-10:raise ValueError('Singular static render transform')
        owned=set(self.vb+[self.ib])
        for name in catalog.by_uri:
            if name in (family_uris or {uri}) or not name.endswith('&mesh'):continue
            data=catalog.read(name)
            if any((s+'\0').encode() in data for s in owned):
                raise ValueError('Template buffers are shared with a mesh outside the selected family')
        for name in owned|{uri,self.family+'?model',self.family+'?render'}:
            _,resource=catalog.get(name)
            if len(resource.fragments)!=(2 if name in owned else 1):
                raise ValueError('Unexpected static resource fragment layout')
        mesh(catalog,uri)

    def _encode(self, source, streams):
        count=len(source.positions)
        if not 3<=count<=65536 or not source.indices or len(source.indices)%3 or len(source.indices)>3_000_000:
            raise ValueError('Static geometry exceeds supported vertex/triangle limits')
        expected=set(streams)-{(1,0)}
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
        encode(streams[1,0],source.positions,3,'f')
        for key in expected:
            rows=source.attributes[key]
            if key==(2,0):
                if any(len(row)!=3 or abs(sum(v*v for v in row)-1)>0.02 for row in rows):
                    raise ValueError('Static normals must be normalized')
                rows=[(*row,0.) for row in rows]
            if key==(3,0):
                if any(len(row)!=4 or abs(sum(v*v for v in row[:3])-1)>0.02 or row[3] not in (-1.,1.) for row in rows):
                    raise ValueError('Static tangents need a unit direction and signed handedness')
            encode(streams[key],rows,4,'B' if key==(6,0) else 'e')
        header=bytearray(self.catalog.read(self.ib));struct.pack_into('<I',header,8,len(source.indices))
        result[self.ib,0]=bytes(header)
        result[self.ib,1]=struct.pack('<'+'H'*len(source.indices),*source.indices)
        # Calculate bounds using quantized positions, matching the emitted buffers.
        points=list(struct.iter_unpack('<3f',result[streams[1,0],1]))
        for i in range(0,len(source.indices),3):
            a,b,c=(points[j] for j in source.indices[i:i+3])
            ab=[b[k]-a[k] for k in range(3)];ac=[c[k]-a[k] for k in range(3)]
            cross=[ab[1]*ac[2]-ab[2]*ac[1],ab[2]*ac[0]-ab[0]*ac[2],ab[0]*ac[1]-ab[1]*ac[0]]
            if sum(v*v for v in cross)<=1e-20:raise ValueError('Triangle collapses at native float precision')
        bounds=[min(p[k] for p in points) for k in range(3)]+[max(p[k] for p in points) for k in range(3)]
        return result,bounds

    def compile(self, source):
        if self.lod_count!=1:raise ValueError('Use the complete LOD family compiler for this template')
        sources=[source] if isinstance(source,StaticInput) else list(source)
        state=_Compilation(self.catalog)
        state.add(self,sources)
        return state.finish(self)

    def source_inputs(self):
        """Read each source primitive with all four UV components and RGBA bytes."""
        _,_,_,indices=buffer(self.catalog,self.ib)
        result=[]
        for part,streams in enumerate(self.parts):
            first,count,base=struct.unpack_from('<3I',self.data,88+88*part)
            raw=struct.unpack_from('<'+'H'*count,indices,first*2)
            remap={};vertices=[];local=[]
            for i in raw:
                if i not in remap:remap[i]=len(vertices);vertices.append(base+i)
                local.append(remap[i])
            values={}
            for key,uri in streams.items():
                stride,n,_,payload=buffer(self.catalog,uri)
                if any(i>=n for i in vertices):raise ValueError('Native attribute index outside source buffer')
                fmt='<3f' if key==(1,0) else '<4B' if key==(6,0) else '<4e'
                rows=[struct.unpack_from(fmt,payload,i*stride) for i in vertices]
                if any(not all(map(math.isfinite,row)) for row in rows):raise ValueError('Non-finite native LOD attribute')
                values[key]=[row[:3] for row in rows] if key==(2,0) else rows
            result.append(StaticInput(values.pop((1,0)),local,values))
        return result


def union_bounds(bounds):
    return [min(b[k] for b in bounds) for k in range(3)]+[max(b[k+3] for b in bounds) for k in range(3)]


def sphere(bounds):
    center=[(bounds[k]+bounds[k+3])/2 for k in range(3)]
    return (*center,math.sqrt(sum((bounds[k+3]-center[k])**2 for k in range(3))))


class _Compilation:
    """Repack shared streams once across all selected material parts and LODs."""
    def __init__(self,catalog):
        self.catalog=catalog;self.groups={};self.indices={};self.fragments={};self.bounds=[];self.owners={}

    def add(self,template,sources):
        if len(sources)!=len(template.parts):
            raise ValueError('Supply one authored primitive for every native material submesh')
        data=bytearray(template.data)
        for part,(streams,source) in enumerate(zip(template.parts,sources)):
            encoded,bounds=template._encode(source,streams)
            position=streams[1,0]
            for key,uri in streams.items():
                owner=(position,key)
                if uri in self.owners and self.owners[uri]!=owner:
                    raise ValueError('Incompatible shared attribute ownership across LODs')
                self.owners[uri]=owner
            group=self.groups.setdefault(position,{'streams':streams,'count':0,'payloads':{u:bytearray() for u in streams.values()}})
            if group['streams']!=streams:
                raise ValueError('Shared position groups require identical companion stream bindings')
            base=group['count'];group['count']+=len(source.positions)
            for uri in streams.values():
                group['payloads'][uri].extend(encoded[uri,1])
                if len(group['payloads'][uri])>64*1024**2:raise ValueError('Compiled stream exceeds 64 MiB budget')
            indices=self.indices.setdefault(template.ib,bytearray());first=len(indices)//2
            indices.extend(encoded[template.ib,1])
            if len(indices)>64*1024**2:raise ValueError('Compiled index stream exceeds 64 MiB budget')
            record=76+88*part
            struct.pack_into('<3I',data,record+12,first,len(source.indices),base)
            struct.pack_into('<4f',data,record+24,*sphere(bounds))
            struct.pack_into('<2I',data,template.draws[part]+8,first,len(source.indices))
            self.bounds.append(bounds)
        self.fragments[template.uri,0]=bytes(data)

    def finish(self,template):
        if set(self.indices)&set(self.owners):raise ValueError('Index and vertex buffers alias')
        for group in self.groups.values():
            for uri,payload in group['payloads'].items():
                header=bytearray(self.catalog.read(uri));struct.pack_into('<I',header,8,group['count'])
                self.fragments[uri,0]=bytes(header);self.fragments[uri,1]=bytes(payload)
        for uri,payload in self.indices.items():
            header=bytearray(self.catalog.read(uri));struct.pack_into('<I',header,8,len(payload)//2)
            self.fragments[uri,0]=bytes(header);self.fragments[uri,1]=bytes(payload)
        model=bytearray(template.model);world=transformed_bounds(union_bounds(self.bounds),template.transform)
        struct.pack_into('<4f',model,16,*sphere(world))
        struct.pack_into('<3f',model,36,*world[:3]);struct.pack_into('<3f',model,48,*world[3:])
        self.fragments[template.family+'?model',0]=bytes(model)
        return self.fragments


class StaticFamily:
    def __init__(self,catalog,family):
        if not family.endswith('.idf') or '?' in family:raise ValueError('Choose a native IDF family')
        model=catalog.read(family+'?model');count=u32(model,0)
        if not 1<=count<=128 or len(model)<64+8*count:raise ValueError('Invalid model LOD table')
        uris={family+f'?lod={i}&mesh' for i in range(count)}
        actual={u for u in catalog.by_uri if u.startswith(family+'?lod=') and u.endswith('&mesh')}
        if actual!=uris:raise ValueError('Native LOD descriptors are incomplete or noncanonical')
        self.templates={i:StaticTemplate(catalog,family+f'?lod={i}&mesh',uris) for i in range(count)}
        self.catalog=catalog;self.family=family

    def compile(self,sources):
        if set(sources)!=set(self.templates) or any(type(i) is not int for i in sources):
            raise ValueError(f'LOD family incomplete: missing {sorted(set(self.templates)-set(sources))}; unexpected {sorted(set(sources)-set(self.templates))}')
        state=_Compilation(self.catalog)
        for i,template in self.templates.items():
            rows=sources[i]
            state.add(template,[rows] if isinstance(rows,StaticInput) else list(rows))
        return state.finish(self.templates[0])


def write_test(catalog, uri, source, destination):
    """Write an isolated full ERP copy for offline inspection; no track/package claim."""
    template=StaticTemplate(catalog,uri)
    sources=[source] if isinstance(source,StaticInput) else list(source)
    replacements=template.compile(sources)
    return _write_test(catalog,uri,replacements,{uri:sources},destination)


def write_family_test(catalog,family,sources,destination):
    templates=StaticFamily(catalog,family)
    sources={i:[parts] if isinstance(parts,StaticInput) else list(parts) for i,parts in sources.items()}
    replacements=templates.compile(sources)
    rows={t.uri:sources[i] for i,t in templates.templates.items()}
    return _write_test(catalog,templates.templates[0].uri,replacements,rows,destination)


def _write_test(catalog,uri,replacements,rows,destination):
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
        triangle_count=0
        for lod,parts in rows.items():
            decoded=mesh(check,lod)
            if decoded.triangles!=sum(len(p.indices)//3 for p in parts):raise ValueError('Generated geometry readback failed')
            triangle_count+=decoded.triangles
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
    return {'vertices':sum(len(p.positions) for parts in rows.values() for p in parts),'triangles':triangle_count,
            'lods':len(rows),'submeshes':sum(len(parts) for parts in rows.values()),'changed_fragments':len(replacements),
            'world_mounted':False,'collision_generated':False,'game_verified':False}
