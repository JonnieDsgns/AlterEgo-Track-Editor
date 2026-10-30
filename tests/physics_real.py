"""Read-only real native collision validation; outputs are private JSON summaries."""
from pathlib import Path
import json,sys,types,time

repo=Path(__file__).resolve().parents[1]
package=types.ModuleType('alterego_track_editor');package.__path__=[str(repo/'addon/alterego_track_editor')];sys.modules['alterego_track_editor']=package
from alterego_track_editor.native_project import TrackDocument
from alterego_track_editor.physics_terrain import PhysicsTerrain

source,output=map(Path,sys.argv[1:3]);start=time.perf_counter();doc=TrackDocument(source);results=[]
try:
    for uri,(_,resource) in list(doc.catalog.by_uri.items()):
        if not uri.endswith('?context=physics_terrain'):continue
        raw=doc.catalog.read(uri);parsed=PhysicsTerrain(raw)
        assert parsed.edit_codes({})==raw
        cell=parsed.cells[0];codes=cell.codes();target='RMBL' if codes[0]!='RMBL' else 'DEFA';codes[0]=target
        edited=parsed.edit_codes({0:codes});check=PhysicsTerrain(edited)
        assert check.cells[0].codes()==codes
        allowed=set(range(cell.offset+80,cell.offset+112))|{cell.offset+cell.triangle+i*4 for i in range(cell.triangles)}
        assert all(a==b or i in allowed for i,(a,b) in enumerate(zip(raw,edited)))
        results.append({'uri':uri,'version':hex(parsed.version),'cells':len(parsed.cells),'triangles':sum(c.triangles for c in parsed.cells),
            'noop_exact':True,'surface_edit_readback':True,'other_bytes_exact':True})
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps({'results':results,'seconds':time.perf_counter()-start,'game_verified':False},indent=2))
    print(json.dumps({'track':source.name,'results':results}))
    assert results,'No supported physics resources'
finally:doc.close()
