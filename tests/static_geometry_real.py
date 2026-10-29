"""Explicit read-only source argument; authored quad written to private output only."""
from pathlib import Path
import collections
import json
import sys
import types

repo=Path(__file__).resolve().parents[1]
package=types.ModuleType('alterego_track_editor')
package.__path__=[str(repo/'addon/alterego_track_editor')]
sys.modules['alterego_track_editor']=package
from alterego_track_editor.native_project import TrackDocument
from alterego_track_editor.static_geometry import StaticTemplate,StaticInput,write_test

source,output=map(Path,sys.argv[1:3])
document=TrackDocument(source)
failures=collections.Counter();tested=0;chosen=None
try:
    for uri in list(document.catalog.by_uri):
        if not uri.endswith('.idf?lod=0&mesh'):continue
        tested+=1
        try:template=StaticTemplate(document.catalog,uri)
        except (ValueError,KeyError) as exc:
            failures[str(exc).split(':')[0]]+=1
            continue
        chosen=template;break
    result={'candidates_checked':tested,'rejections':dict(failures),'game_verified':False}
    if chosen:
        positions=[(0.,0.,0.),(4.,0.,0.),(4.,2.,0.),(0.,2.,0.)]
        values={(2,0):[(0.,0.,1.)]*4,(3,0):[(1.,0.,0.,1.)]*4,
            (5,0):[(0.,0.,0.,0.),(1.,0.,0.,0.),(1.,1.,0.,0.),(0.,1.,0.,0.)],
            (5,1):[(0.,0.,0.,0.)]*4,(6,0):[(255,255,255,255)]*4}
        authored=[StaticInput(positions,[0,1,2,0,2,3],{k:values[k] for k in streams if k!=(1,0)}) for streams in chosen.parts]
        result['template']=chosen.uri
        result['report']=write_test(document.catalog,chosen.uri,authored,output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.with_suffix('.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
    assert chosen is not None,'No compatible single-LOD/single-submesh template found'
finally:document.close()
