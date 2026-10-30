"""Read-only real-layer deletion check; outputs are private JSON summaries.

Arguments: native track folder, output JSON, optional SwoftyLauncher checkout for an independent
serializer comparison using its tools/pkg.py.
"""
from pathlib import Path
import collections,importlib.util,json,sys,time,types

repo=Path(__file__).resolve().parents[1]
package=types.ModuleType('alterego_track_editor');package.__path__=[str(repo/'addon/alterego_track_editor')];sys.modules['alterego_track_editor']=package
from alterego_track_editor.native_project import TrackDocument
from alterego_track_editor.native.formats.pkg import Document,plain

source,output=map(Path,sys.argv[1:3]);swofty=Path(sys.argv[3]) if len(sys.argv)>3 else None
start=time.perf_counter();doc=TrackDocument(source)
try:
    reasons=collections.Counter()
    for r in doc.records:
        reason=doc.deletion_reason(r,allow_pvs=False) or 'deletable without PVS opt-in'
        reasons[reason.split(';')[0].split(' (')[0]]+=1
    props=[r for r in doc.records if not doc.deletion_reason(r,allow_pvs=True)]
    by_layer=collections.defaultdict(list)
    for r in props:by_layer[r['layer']].append(r)
    uri=max(by_layer,key=lambda u:len(by_layer[u]))
    plain_prop=next((r for r in by_layer[uri] if r['name'] not in doc.pvs_names()),None)
    pvs_prop=next(r for r in by_layer[uri] if r['name'] in doc.pvs_names())
    chosen=[r for r in (plain_prop,pvs_prop) if r]
    replacements=doc.apply({},deletions=[r['id'] for r in chosen],allow_pvs_deletions=True)
    after=plain(Document(replacements[uri]).root)['instances'];before=plain(doc.layers[uri]['doc'].root)['instances']
    removed={r['index'] for r in chosen}
    assert after==[item for i,item in enumerate(before) if i not in removed]
    result={'track':source.name,'records':len(doc.records),'deletion_eligibility':dict(reasons),'layer':uri,
        'deleted':doc.deleted,'readback_exact':True,'composable_available':doc.layer_edits[uri] is not None,'game_verified':False}
    if swofty:
        spec=importlib.util.spec_from_file_location('swofty_pkg',swofty/'tools/pkg.py');sw=importlib.util.module_from_spec(spec);spec.loader.exec_module(sw)
        pkg=sw.Pkg(doc.layers[uri]['doc'].data);items=pkg.root['instances'].items
        names={r['name'] for r in chosen};pkg.root['instances'].items=[e for e in items if e['name'].value not in names]
        result['swofty_python_serializer_exact']=pkg.to_bytes()==replacements[uri]
        assert result['swofty_python_serializer_exact']
    result['seconds']=round(time.perf_counter()-start,2)
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2));print(json.dumps(result))
finally:doc.close()
