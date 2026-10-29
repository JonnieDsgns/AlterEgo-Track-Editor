"""Independent static family construction with typed URI-pool relocation.

No arbitrary replacement of bytes in opaque resources. Materials remain explicit
external dependencies; this is an asset ERP, not a complete track package.
"""
import hashlib
import re
import struct
import json
import tempfile
import shutil
from pathlib import Path
from .native.geometry import u32,cstring,region
from .native.materials import binding_table
from .static_geometry import StaticFamily
from .native.storage import Catalog


def relocate_mesh(data,mapping):
    vb,ib,end=[76+u32(data,p) for p in (20,24,28)]
    def rewrite(start,stop):
        rows=[]
        while start<stop:
            uri=cstring(data,start,stop)
            if uri not in mapping:raise ValueError('Mesh references a buffer outside the authored family')
            rows.append(mapping[uri].encode()+b'\0');start+=len(uri.encode())+1
        return b''.join(rows)
    vertices,indices=rewrite(vb,ib),rewrite(ib,end)
    result=bytearray(data[:vb]+vertices+indices+data[end:])
    delta=len(vertices)+len(indices)-(end-vb)
    struct.pack_into('<I',result,24,vb+len(vertices)-76)
    for p in (28,32,40,44,60):struct.pack_into('<I',result,p,u32(data,p)+delta)
    if u32(data,48) and delta:raise ValueError('Templates with opaque extra records require equal-length resource identities')
    if 76+u32(data,52)>=end:struct.pack_into('<I',result,52,u32(data,52)+delta)
    return bytes(result)


def relocate_model(data,mapping):
    lods=u32(data,0)
    bones,secondary=struct.unpack_from('<HH',data,4)
    start=64+8*lods+120*bones+2*secondary
    region(data,0,start);end=start;pool=[]
    for _ in range(lods):
        uri=cstring(data,end)
        if uri not in mapping:raise ValueError('Model LOD pool references an unexpected resource')
        pool.append(mapping[uri].encode()+b'\0');end+=len(uri.encode())+1
    return data[:start]+b''.join(pool)+data[end:]


def choose_identity(catalog,family,requested):
    """Keep opaque extra-record addresses stable using deterministic identity padding."""
    template=StaticFamily(catalog,family)
    if not any(u32(t.data,48) for t in template.templates.values()):return requested
    if len(requested.encode())>len(family.encode()):
        raise ValueError('This template needs a shorter asset name to preserve opaque record addresses')
    size=len(family.encode())-len(requested.encode())
    if size:
        suffix=hashlib.sha256(requested.encode()).hexdigest()
        requested=requested[:-4]+(suffix*((size+63)//64))[:size]+'.idf'
    return requested


def build_asset(catalog,family,target,sources,binding):
    if not re.fullmatch(r'eaid://[a-z0-9_/-]+\.idf',target) or any(p in ('','.','..') for p in target[7:].split('/')):
        raise ValueError('Choose a lowercase absolute eaid IDF family without traversal or queries')
    if target==family:raise ValueError('New asset must have an independent identity')
    template=StaticFamily(catalog,family);compiled=template.compile(sources)
    names={family+'?model',family+'?render'}
    for t in template.templates.values():names.update([t.uri,t.ib,*t.vb])
    if any(not n.startswith(family+'?') for n in names):raise ValueError('Template streams outside their IDF family are unsupported')
    mapping={name:target+name[len(family):] for name in names}
    new_binding=target[:-4]+'.emb?context=default'
    if any(n in catalog.by_uri for n in [*mapping.values(),new_binding]):raise ValueError('Target asset identity already exists')
    _,context=catalog.get(binding)
    if context.type_name!='GfxMatBindRes' or len(context.fragments)!=1:raise ValueError('Choose a native material binding context')
    raw=catalog.read(binding);entries=binding_table(raw)
    if len(entries)!=u32(raw,0):raise ValueError('Duplicate native material slot names')
    if any(slot not in entries for t in template.templates.values() for slot in t.slots):
        raise ValueError('Native material context does not cover every LOD slot')
    resources=[]
    for name in sorted(names):
        _,resource=catalog.get(name)
        fragments=[compiled.get((name,i),catalog.read(name,i)) for i in range(len(resource.fragments))]
        if name.endswith('&mesh'):fragments[0]=relocate_mesh(fragments[0],mapping)
        elif name.endswith('?model'):fragments[0]=relocate_model(fragments[0],mapping)
        resources.append((mapping[name],resource,fragments))
    resources.append((new_binding,context,[raw]))
    dependencies=[{'uri':uri,'available_in_catalog':uri in catalog.by_uri} for uri in sorted(set(entries.values()))]
    report={'family':target,'model':target+'?context=render','binding':new_binding,
        'source_family':family,'lods':len(template.templates),'material_dependencies':dependencies,
        'dependency_closure_complete':False,'world_mounted':False,'collision_generated':False,'game_verified':False}
    return resources,report


def archive_bytes(resources,header=None):
    """Stored ERPK fragments; retain source resource kinds, unknown bytes and flags."""
    if sum(len(raw) for _,_,fragments in resources for raw in fragments)>256*1024**2:raise ValueError('Asset archive exceeds output budget')
    entries=bytearray();payload=bytearray();seen=set();fragment_count=0
    for name,source,fragments in resources:
        if name in seen:raise ValueError('Duplicate output resource identity')
        seen.add(name);encoded=name.encode()+b'\0'
        if len(encoded)>65535:raise ValueError('Resource identity is too long')
        entry=bytearray(struct.pack('<H',len(encoded))+encoded+source.kind+source.unknown+bytes([len(fragments)]))
        for index,raw in enumerate(fragments):
            fragment=source.fragments[index]
            entry.extend(fragment.name+struct.pack('<QQIBQ',len(payload),len(raw),fragment.flags,0x91,len(raw)))
            payload.extend(raw);fragment_count+=1
        entry.extend(hashlib.md5(b''.join(fragments)).digest());entries.extend(struct.pack('<I',len(entry))+entry)
    info=struct.pack('<II',len(resources),fragment_count)+entries
    header=bytearray(header if header is not None else b'ERPK'+struct.pack('<I',3)+b'\0'*40)
    struct.pack_into('<QQQ',header,16,48,len(info),48+len(info))
    return bytes(header+info+payload)


def write_asset(catalog,family,target,sources,binding,destination,bundle=False):
    destination=Path(destination).expanduser().resolve()
    if destination.exists():raise ValueError('Choose a new asset output folder')
    if any((p/'F1_25.exe').exists() for p in (destination,*destination.parents)):
        raise ValueError('Choose an output outside the game installation')
    if any(destination.is_relative_to(Path(p).resolve()) for p in catalog.asset_roots):
        raise ValueError('Choose an output outside the source asset roots')
    resources,report=build_asset(catalog,family,target,sources,binding)
    from .asset_dependencies import dependency_plan
    dependencies,files,graph=dependency_plan(catalog,[d['uri'] for d in report['material_dependencies']],bundle)
    resources.extend(dependencies)
    report['dependency_plan']=graph
    report['dependency_closure_complete']=graph['dependency_closure_complete']
    payload=archive_bytes(resources,catalog.get(family+'?model')[0].header)
    if len(payload)+sum(f['identity'][0] for f in files if bundle)>512*1024**2:raise ValueError('Asset output exceeds 512 MiB budget')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ate-asset-',dir=destination.parent) as folder:
        file=Path(folder)/'asset.erp';file.write_bytes(payload)
        check=Catalog();check.mount(file)
        family_check=StaticFamily(check,target)
        from .native.geometry import mesh
        triangles=[]
        for level,template in family_check.templates.items():triangles.append(mesh(check,template.uri).triangles)
        for name,_,fragments in resources:
            for index,raw in enumerate(fragments):
                if check.read(name,index)!=raw:raise ValueError('Independent asset fragment readback failed')
        report['triangles']=triangles;report['archive_sha256']=hashlib.sha256(payload).hexdigest()
        staged_files=[]
        if bundle:
            for info in files:
                source=info['source'];before=source.stat()
                if (before.st_size,before.st_mtime_ns)!=info['identity']:raise ValueError('Mip source changed; reopen before exporting')
                local='mips/'+info['path'];staged=Path(folder)/local;staged.parent.mkdir(parents=True,exist_ok=True)
                digest=hashlib.sha256()
                with source.open('rb') as src,staged.open('xb') as out:
                    while block:=src.read(1024*1024):out.write(block);digest.update(block)
                after=source.stat()
                if (after.st_size,after.st_mtime_ns)!=info['identity'] or staged.stat().st_size!=before.st_size:
                    raise ValueError('Mip source changed while exporting')
                staged_files.append((local,staged));info['sha256']=digest.hexdigest()
            report['mip_files']=[{'native_path':i['path'],'file':'mips/'+i['path'],'sha256':i['sha256'],'bytes':i['identity'][0]} for i in files]
            check.asset_roots=[Path(folder)/'mips']
            _,_,reopened=dependency_plan(check,[d['uri'] for d in report['material_dependencies']],False)
            if reopened['errors']:raise ValueError('Bundled dependency graph failed staged readback')
            report['bundled_dependency_readback']=True
        manifest=json.dumps(report,indent=2).encode()
        # Publish from staging while its file snapshots still exist.
        destination.mkdir()
        created=[];directories=[]
        try:
            for name,data in [('asset.erp',payload),('asset.json',manifest)]:
                with (destination/name).open('xb') as out:created.append(destination/name);out.write(data)
            for local,staged in staged_files:
                dest=destination/local
                for parent in reversed(dest.parent.relative_to(destination).parents):
                    candidate=destination/parent
                    if candidate!=destination and not candidate.exists():candidate.mkdir();directories.append(candidate)
                if not dest.parent.exists():dest.parent.mkdir();directories.append(dest.parent)
                with staged.open('rb') as src,dest.open('xb') as out:created.append(dest);shutil.copyfileobj(src,out)
        except BaseException:
            for output in reversed(created):output.unlink(missing_ok=True)
            for directory in reversed(directories):
                try:directory.rmdir()
                except OSError:pass
            try:destination.rmdir()
            except OSError:pass
            raise
    return report
