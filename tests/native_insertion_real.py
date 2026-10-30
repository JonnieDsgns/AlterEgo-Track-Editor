"""Read-only real-layer insertion check; outputs are private JSON summaries and one private archive copy.

Arguments: native track folder, output JSON, optional SwoftyLauncher checkout for an independent
serializer replay using its tools/pkg.py (the Rust launcher build is not executed here).
"""
from pathlib import Path
import collections,copy,hashlib,importlib.util,json,sys,time,types

repo=Path(__file__).resolve().parents[1]
package=types.ModuleType('alterego_track_editor');package.__path__=[str(repo/'addon/alterego_track_editor')];sys.modules['alterego_track_editor']=package
from alterego_track_editor.native_project import TrackDocument
from alterego_track_editor.native.formats.pkg_tree import Tree,float32
from alterego_track_editor.native.formats.erp import Erp

source,output=map(Path,sys.argv[1:3]);swofty=Path(sys.argv[3]) if len(sys.argv)>3 else None
start=time.perf_counter();doc=TrackDocument(source)
try:
    canonical=collections.Counter(Tree(info['doc'].data).canonical for info in doc.layers.values())
    reasons=collections.Counter(r['clone_reason'] or 'cloneable' for r in doc.records)
    by_layer=collections.defaultdict(list)
    for r in doc.records:by_layer[r['layer']].append(r)
    # Largest layer holding a cloneable prop, with a different editable record to move.
    uri=max((u for u,rs in by_layer.items() if any(not r['clone_reason'] and not r['render_error'] for r in rs)),key=lambda u:len(by_layer[u]))
    source_record=next(r for r in by_layer[uri] if not r['clone_reason'] and not r['render_error'])
    other=next(r for r in by_layer[uri] if r is not source_record and r['editable'] and not r['render_error'])
    move=other['world'][:];move[13]+=0.25
    world=source_record['world'][:];world[12]+=3.5
    identity=hashlib.sha256(b'real-insertion-check').hexdigest()[:32]
    replacements=doc.apply({other['id']:move},[{'id':identity,'source':source_record['id'],'world':world}])
    data=replacements[uri];edits=doc.layer_edits[uri]
    result={'track':source.name,'layers':len(doc.layers),'canonical_layers':canonical[True],'non_canonical_layers':canonical[False],
        'records':len(doc.records),'clone_eligibility':dict(reasons),'layer':uri,'source':source_record['name'],
        'moved':other['name'],'inserted':doc.inserted,'edits':[e['op'] for e in edits],'own_replay_exact':True,'game_verified':False}
    if swofty:
        spec=importlib.util.spec_from_file_location('swofty_pkg',swofty/'tools/pkg.py');sw=importlib.util.module_from_spec(spec);spec.loader.exec_module(sw)
        pkg=sw.Pkg(doc.layers[uri]['doc'].data);entries=pkg.root['instances'].items
        find=lambda name:next(e for e in entries if e['name'].value==name)
        find(other['name'])['overrides']['WorldObject'].set('transform',sw.Val('mat4',float32(move)))
        clone=copy.deepcopy(find(source_record['name']));inserted=doc.inserted[0]
        clone.set('name',sw.Val('stri',inserted['name']));clone.set('uniqueid',sw.Val('woid',inserted['uniqueid']))
        clone['overrides']['WorldObject'].set('transform',sw.Val('mat4',float32(world)));entries.append(clone)
        result['swofty_python_serializer_exact']=pkg.to_bytes()==data
        assert result['swofty_python_serializer_exact'],'Swofty serializer replay differs'
    # Archive integration on one real archive copy in private storage; source stays untouched.
    archives,_=doc._locations(replacements)
    rel=sorted(archives,key=lambda r:(source/r).stat().st_size)[0];before=hashlib.sha256((source/rel).read_bytes()).hexdigest()
    target=output.parent/(output.stem+'-'+rel.name);target.parent.mkdir(parents=True,exist_ok=True)
    archive=Erp(source/rel);archive.replace_fragment(uri,0,data);archive.write(target)
    check=Erp(target);result['archive_readback']=check.fragment_data(uri,0)==data
    original=Erp(source/rel)
    result['archive_other_resources_exact']=all(check.fragment_data(r.name,i)==original.fragment_data(r.name,i)
        for r in original.resources if r.name!=uri for i in range(len(r.fragments)))
    result['source_unchanged']=hashlib.sha256((source/rel).read_bytes()).hexdigest()==before
    assert result['archive_readback'] and result['archive_other_resources_exact'] and result['source_unchanged']
    result['seconds']=round(time.perf_counter()-start,2)
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2));print(json.dumps(result))
finally:doc.close()
