"""Read Swofty track data into a private view; never install or execute addons."""
import json
from pathlib import Path, PurePosixPath
import tempfile
import zipfile
import shutil
from .storage import Catalog
from .scene import open_track, Scene


def contained(root, relative):
    rel=PurePosixPath(str(relative).replace('\\','/'))
    if rel.is_absolute() or '..' in rel.parts or ':' in str(rel):raise ValueError('Unsafe addon path')
    path=(root/str(rel)).resolve()
    if not path.is_relative_to(root.resolve()):raise ValueError('Addon path escapes package')
    return path


def read_json(path):
    if path.stat().st_size>8*1024*1024:raise ValueError('Addon JSON exceeds 8 MiB')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def open_addon(source, variant='f1', base=None, catalog_only=False):
    source=Path(source).resolve();temporary=None
    if source.is_dir():root=source
    else:
        temporary=tempfile.TemporaryDirectory(prefix='trackview-addon-');root=Path(temporary.name)
        try:
            with zipfile.ZipFile(source) as archive:
                infos=archive.infolist()
                if len(infos)>20000 or sum(i.file_size for i in infos)>4*1024**3:raise ValueError('Addon exceeds package budget')
                targets=set()
                for info in infos:
                    path=contained(root,info.filename)
                    if path in targets:raise ValueError('Duplicate addon archive path')
                    targets.add(path)
                    if info.is_dir():continue
                    if info.file_size>2*1024**3 or info.file_size>max(1024**2,info.compress_size*1000):raise ValueError('Addon member exceeds unpack budget')
                    if (info.external_attr>>16)&0o170000==0o120000:raise ValueError('Addon symlinks unsupported')
                    path.parent.mkdir(parents=True,exist_ok=True)
                    with archive.open(info) as src,path.open('xb') as dst:shutil.copyfileobj(src,dst,1024*1024)
        except Exception:
            temporary.cleanup()
            raise
    manifest=read_json(root/'swofty.json');operations=manifest.get('operations',{})
    catalog=Catalog();catalog.asset_roots=[root];warnings=[];ops=[];track_packages=[]
    for kind in ('erp','assets'):
        for name in operations.get(kind,[]):
            document=read_json(contained(root,name))
            ops.extend(document.get('ops',[]))
    # File copies are represented in our own staging tree, never in the installation.
    virtual=tempfile.TemporaryDirectory(prefix='trackview-track-');virtualroot=Path(virtual.name)
    for operation in operations.get('files',[]):
        src=contained(root,operation['source']);dst=contained(virtualroot,operation['target'])
        if src.is_dir():raise ValueError('Directory file copies need an unpacked track folder')
        dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
    catalog.asset_roots.insert(0,virtualroot)
    for operation in ops:
        kind=operation.get('op','').removeprefix('erp.')
        if kind=='track.add':
            package_root=contained(root,operation['source']);package=read_json(package_root/'manifest.json')
            code=package['track_code']
            if not code or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789_' for c in code):raise ValueError('Invalid track code')
            catalog.mount(contained(package_root,package['erp']))
            track_packages.append((package_root,package))
            if not hasattr(catalog,'asset_mappings'):catalog.asset_mappings=[]
            if not hasattr(catalog,'mip_files'):catalog.mip_files={}
            for mapping in package.get('copy_directories',[]):
                source_dir=contained(package_root,mapping['source']);prefix=mapping['destination'].replace('\\','/').strip('/')+'/'
                contained(virtualroot,prefix)
                for child in source_dir.rglob('*'):
                    if child.is_file():
                        checked=contained(root,child.relative_to(root))
                        if child.name in catalog.mip_files:raise ValueError('Ambiguous shipped mip filename')
                        catalog.mip_files[child.name]=checked
                        if len(catalog.mip_files)>20000:raise ValueError('Too many shipped mips')
                catalog.asset_mappings.append((prefix,source_dir))
                if prefix.startswith('asset_groups/'):catalog.asset_mappings.append(('2025_'+prefix,source_dir))
            catalog.asset_roots.append(package_root)
        elif kind in ('overlay','put-resource','copy-resource') and operation.get('source','').lower().endswith('.erp'):
            file=contained(root,operation['source']);catalog.mount(file)
            archive=catalog.archives[-1]
            if kind=='overlay':
                for resource in archive.resources:catalog.by_uri[resource.name]=(archive,resource)
            else:
                name=operation['resource'];resource=next((r for r in archive.resources if r.name==name),None)
                if resource is None:raise ValueError('Addon resource not found: '+name)
                catalog.by_uri[operation.get('as',name)]=(archive,resource)
        elif kind=='replace-resource':
            file=contained(root,operation['source']);stat=file.stat()
            catalog.fragments[operation['resource'],operation.get('fragment',0)]=(file,(stat.st_size,stat.st_mtime_ns))
        elif kind=='add-mipmaps':
            src=contained(root,operation['source']);dst=contained(virtualroot,operation['target'])
            dst.parent.mkdir(parents=True,exist_ok=True)
            if src.is_dir():
                for child in src.rglob('*'):
                    if child.is_file():
                        checked=contained(root,child.relative_to(root));out=contained(dst,child.relative_to(src));out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(checked,out)
            else:shutil.copyfile(src,dst)
        else:warnings.append(dict(name=kind,reason='Addon operation not applied in static preview'))
    candidates=[]
    for search in (virtualroot,root):
        for file in search.rglob('*_'+variant+'.erp'):
            if file.parent.name=='wep' and file.parent.parent not in candidates:candidates.append(file.parent.parent)
    if len(track_packages)>1:raise ValueError('This addon contains multiple tracks; open one track package folder')
    if track_packages:
        folder=virtualroot/track_packages[0][1]['track_code']
        if base:
            base_folder=Path(base).expanduser().resolve()
            for file in (base_folder/'wep'/f'{base_folder.name}_{variant}.erp',base_folder/'wep'/f'{base_folder.name}_common.erp',base_folder/f'{base_folder.name}_common.erp'):
                if file.is_file():catalog.mount(file)
    else:folder=Path(base).expanduser().resolve() if base else (candidates[0] if len(candidates)==1 else None)
    if folder is None:raise ValueError('Select the matching base track folder for this addon (package has no single complete track tree)')
    # Full addon archives override base files with the same resource URI.
    for candidate in candidates:
        for file in (candidate/'wep'/f'{candidate.name}_{variant}.erp',candidate/'wep'/f'{candidate.name}_common.erp',candidate/f'{candidate.name}_common.erp'):
            if file.is_file():catalog.mount(file)
    if catalog_only:
        scene=Scene();scene.catalog=catalog;scene.materials.catalog=catalog
    else:
        scene=open_track(folder,variant,catalog=catalog)
    scene._addon_temp=(temporary,virtual)
    scene.title=manifest.get('name',manifest.get('id',source.stem))+' / '+variant
    scene.warnings.extend(warnings)
    scene.sources.append(str(source));scene.source_identities[str(source/'swofty.json' if source.is_dir() else source)]=((source/'swofty.json' if source.is_dir() else source).stat().st_size,(source/'swofty.json' if source.is_dir() else source).stat().st_mtime_ns)
    for archive in catalog.archives:
        if str(archive.path) not in scene.sources:scene.sources.append(str(archive.path))
    if base:
        game_root=next((p for p in Path(base).expanduser().resolve().parents if (p/'F1_25.exe').is_file()),None)
        if game_root:catalog.asset_roots.append(game_root)
    return scene
