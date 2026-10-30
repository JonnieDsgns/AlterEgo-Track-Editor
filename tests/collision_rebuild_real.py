"""Read-only real check: whole native modern collision rebuilt as legacy JPAK (in memory); private JSON summary."""
from pathlib import Path
import collections,json,struct,sys,time,types

repo=Path(__file__).resolve().parents[1]
package=types.ModuleType('alterego_track_editor');package.__path__=[str(repo/'addon/alterego_track_editor')];sys.modules['alterego_track_editor']=package
from alterego_track_editor.native_project import TrackDocument
from alterego_track_editor.physics_terrain import PhysicsTerrain,build_legacy,triangle_soup,code_words

source,output=map(Path,sys.argv[1:3]);start=time.perf_counter();doc=TrackDocument(source)
try:
    uris=sorted({r['physics'] for r in doc.records if r['physics']})
    assert len(uris)==1,uris
    native=PhysicsTerrain(doc.catalog.read(uris[0]));soup=list(triangle_soup(native.cells))
    codes=sorted({t[3] for t in soup});built=time.perf_counter()
    raw=build_legacy(soup,codes=codes,words=code_words(native));elapsed=time.perf_counter()-built
    legacy=PhysicsTerrain(raw,0x20002)
    depths=collections.Counter();roots=collections.Counter()
    for cell in legacy.cells:
        stack=[(0,0)];roots[struct.unpack_from('>H',cell.data,cell.node)[0]<0x8000]+=1
        while stack:
            index,depth=stack.pop();word=struct.unpack_from('>H',cell.data,cell.node+2*index)[0]
            if word<0x8000:stack.extend((k,depth+1) for k in range(word,word+4))
            elif word!=0xffff:depths[depth]+=1
    result={'track':source.name,'uri':uris[0],'native_version':hex(native.version),'native_cells':len(native.cells),'triangles':len(soup),
        'codes':codes,'legacy_cells':len(legacy.cells),'legacy_bytes':len(raw),'native_bytes':len(native.data),
        'max_triangles_per_cell':max(c.triangles for c in legacy.cells),'max_vertices_per_cell':max(c.vertices for c in legacy.cells),
        'internal_roots':roots[True],'leaf_depths':dict(sorted(depths.items())),'geometry_readback':'exact multiset (builder check)',
        'build_seconds':round(elapsed,1),'total_seconds':round(time.perf_counter()-start,1),'game_verified':False}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2));print(json.dumps(result))
finally:doc.close()
