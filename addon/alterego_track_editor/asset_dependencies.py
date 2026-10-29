"""Typed material/texture dependency planning; native shaders remain explicit externals."""
from collections import deque
import hashlib
from pathlib import Path,PurePosixPath
import struct
from .native.geometry import u32,cstring,region
from .native.materials import external_mips


def material_edges(data):
    count=u32(data,0)
    if count>100000:raise ValueError('Too many material inputs')
    base=32+36*count;region(data,0,base)
    numeric,shader,names,primary,secondary,tail=[u32(data,k) for k in (8,12,16,20,24,28)]
    if not 0<=numeric<=shader<=names<=primary<=secondary<=tail<=len(data)-base:
        raise ValueError('Invalid material sections')
    result=[('shader',cstring(data,base+shader,base+names))]
    for i in range(count):
        p=32+36*i;usage,kind=u32(data,p+4),u32(data,p+8)
        label=cstring(data,base+names+u32(data,p),base+primary)
        if kind==2 or (kind==6 and usage==2):
            size,offset=u32(data,p+16),u32(data,p+28)
            for role,start,end in [('primary',primary,secondary),('secondary',secondary,tail)]:
                if not size or offset+size>end-start:raise ValueError('Material texture path outside its section')
                raw=bytes(region(data,base+start+offset,size))
                if raw[-1:]!=b'\0' or b'\0' in raw[:-1]:raise ValueError('Invalid sized texture path')
                uri=raw[:-1].decode('utf-8')
                if uri:result.append((label+':'+role,uri))
    if not result[0][1]:raise ValueError('Material has no shader reference')
    return result


def mip_path(value):
    value=value.replace('\\','/')
    if not value or ':' in value or value.startswith('/') or any(p in ('','.','..') for p in value.split('/')):
        raise ValueError('Unsafe external texture path')
    reserved={'CON','PRN','AUX','NUL'}|{prefix+str(i) for prefix in ('COM','LPT') for i in range(1,10)}
    if any(p.rstrip('. ')!=p or any(c in p for c in '<>"|?*\0\r\n') or p.split('.')[0].upper() in reserved for p in value.split('/')):
        raise ValueError('Unsafe Windows texture path')
    return PurePosixPath(value).as_posix()


def locate_mip(catalog,path):
    path=mip_path(path);candidates=set()
    for prefix,directory in getattr(catalog,'asset_mappings',[]):
        if path.startswith(prefix):
            root=Path(directory).resolve();file=(root/path[len(prefix):]).resolve()
            if not file.is_relative_to(root):raise ValueError('External texture mapping escapes its source')
            if file.is_file():return file
    basename=path.rsplit('/',1)[-1];hashed=hashlib.md5(path.encode()).hexdigest()[:12]+'_'+basename
    for name in (hashed,basename):
        file=getattr(catalog,'mip_files',{}).get(name)
        if file and Path(file).is_file():return Path(file).resolve()
    for root in catalog.asset_roots:
        root=Path(root).resolve();file=(root/path).resolve()
        if file.is_relative_to(root) and file.is_file():candidates.add(file)
    if len(candidates)!=1:raise ValueError('External mip is missing or ambiguous: '+path)
    return candidates.pop()


def dependency_plan(catalog,roots,bundle=False):
    queue=deque((uri,False) for uri in sorted(set(roots)))
    nodes={};edges=[];resources=[];files={};errors=[];external_shaders=set();total=0
    while queue:
        uri,shader=queue.popleft()
        if not uri.startswith('eaid://') or any(c in uri for c in '\r\n\0'):
            raise ValueError('Invalid native dependency URI')
        if uri in nodes:
            if shader and nodes[uri]['role']!='shader':raise ValueError('Conflicting dependency roles')
            if not shader and nodes[uri]['role']=='shader':raise ValueError('Conflicting dependency roles')
            continue
        if len(nodes)>=20000:raise ValueError('Dependency graph exceeds resource budget')
        node={'uri':uri,'role':'shader' if shader else 'resource','bundled':False};nodes[uri]=node
        if shader:
            node['status']='EXTERNAL_SHADER';node['available_in_catalog']=uri in catalog.by_uri
            external_shaders.add(uri)
            continue
        if uri not in catalog.by_uri:
            node['status']='MISSING';errors.append(uri+': missing resource');continue
        archive,resource=catalog.get(uri);archive._unchanged_source()
        node['type']=resource.type_name;node['source_digest']=resource.hash.hex()
        try:
            kind=resource.type_name;data=catalog.read(uri);dependencies=[]
            if 'material' in kind.lower():
                if len(resource.fragments)!=1:raise ValueError('Unsupported material fragments')
                dependencies=material_edges(data)
            elif kind=='GfxSRVResource':
                if len(resource.fragments)!=1:raise ValueError('Unsupported texture-view fragments')
                target=cstring(data,24);end=24+len(target.encode())+1
                if any(data[end:]):raise ValueError('Unknown texture-view trailer')
                dependencies=[('surface',target)]
            elif kind=='GfxSurfaceRes':
                if len(data) not in (36,40) or u32(data,28)!=1 or len(resource.fragments) not in (2,3):
                    raise ValueError('Unsupported texture surface layout')
                if len(resource.fragments)==3:
                    meta=catalog.read(uri,2)
                    if not meta:raise ValueError('Empty external mip descriptor')
                    path,records=external_mips(meta)
                    if records:
                        path=mip_path(path);file=locate_mip(catalog,path);stat=file.stat()
                        if stat.st_size>256*1024**2 or any(offset+packed>stat.st_size for _,offset,packed,_ in records):
                            raise ValueError('External mip range exceeds file/budget')
                        key=path.casefold()
                        if key in files and files[key]['path']!=path:raise ValueError('Case-colliding external mip paths')
                        if key in files and files[key]['source']!=file:raise ValueError('Ambiguous external mip source')
                        files[key]={'path':path,'source':file,'identity':(stat.st_size,stat.st_mtime_ns)}
            else:raise ValueError('Unsupported dependency resource type: '+kind)
            for role,target in dependencies:
                if len(edges)>=100000:raise ValueError('Dependency graph exceeds edge budget')
                edges.append({'from':uri,'to':target,'role':role});queue.append((target,role=='shader'))
            node['status']='BUNDLED' if bundle else 'EXTERNAL_REQUIRED'
            if bundle:
                fragments=[catalog.read(uri,i) for i in range(len(resource.fragments))]
                total+=sum(map(len,fragments))
                if total>256*1024**2:raise ValueError('Dependency payload budget exceeded')
                resources.append((uri,resource,fragments));node['bundled']=True
        except (ValueError,IndexError,struct.error,OSError) as exc:
            node['status']='UNSUPPORTED';errors.append(uri+': '+str(exc))
    if bundle and errors:raise ValueError('Cannot bundle dependency graph: '+errors[0])
    report={'nodes':list(nodes.values()),'edges':edges,'errors':errors,
        'external_shaders':sorted(external_shaders),'bundle_materials_textures':bundle,
        'dependency_graph_complete':not errors and not external_shaders,
        'dependency_closure_complete':bundle and not errors and not external_shaders,
        'shader_dependencies_transitive':'unverified; retained as native external packages',
        'external_mips':[{'path':f['path'],'bytes':f['identity'][0],'bundled':bundle} for f in files.values()]}
    return resources,list(files.values()),report
