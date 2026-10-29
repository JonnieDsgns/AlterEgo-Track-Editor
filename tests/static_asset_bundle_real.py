"""Read-only real template scan; authored geometry outputs remain private."""
from pathlib import Path
import collections
import json
import sys
import types

repo=Path(__file__).resolve().parents[1]
package=types.ModuleType('alterego_track_editor');package.__path__=[str(repo/'addon/alterego_track_editor')]
sys.modules['alterego_track_editor']=package
from alterego_track_editor.native_project import TrackDocument
from alterego_track_editor.static_geometry import StaticFamily,StaticInput,write_family_test
from alterego_track_editor.static_asset import write_asset,choose_identity

source,output=map(Path,sys.argv[1:3]);document=TrackDocument(source)
failures=collections.Counter();checked=0;results=[]
try:
    for uri in list(document.catalog.by_uri):
        if not uri.endswith('.idf?model'):continue
        checked+=1;family=uri[:-len('?model')]
        try:templates=StaticFamily(document.catalog,family)
        except (ValueError,KeyError) as exc:
            failures[str(exc).split(':')[0]]+=1;continue
        coverage={'multi_lod':len(templates.templates)>1,'multi_material':any(len(t.parts)>1 for t in templates.templates.values())}
        if not any(coverage.values()):continue
        if results and not any(value and not any(row['coverage'][key] for row in results) for key,value in coverage.items()):continue
        rows={}
        for lod,template in templates.templates.items():
            rows[lod]=[]
            for part,streams in enumerate(template.parts):
                offset=part*10+lod
                positions=[(offset,0.,0.),(offset+4.,0.,0.),(offset+4.,2.,0.),(offset,2.,0.)]
                values={(2,0):[(0.,0.,1.)]*4,(3,0):[(1.,0.,0.,1.)]*4,
                    (5,0):[(0.,0.,0.,0.),(1.,0.,0.,0.),(1.,1.,0.,0.),(0.,1.,0.,0.)],
                    (5,1):[(0.,0.,0.,0.)]*4,(6,0):[(255,255,255,255)]*4}
                rows[lod].append(StaticInput(positions,[0,1,2,0,2,3],{k:values[k] for k in streams if k!=(1,0)}))
        target=output.with_name(output.stem+'-'+str(len(results))+'.erp')
        binding=next(r['binding'] for r in document.records if r['model']==family+'?context=render')
        identity=choose_identity(document.catalog,family,'eaid://environment_package/tracks/custom/objects/new.idf')
        report=write_asset(document.catalog,family,identity,rows,binding,target.with_suffix(''),True)
        results.append({'template':family,'coverage':coverage,'report':report})
        if all(any(row['coverage'][key] for row in results) for key in coverage):break
    result={'candidates_checked':checked,'rejections':dict(failures),'results':results,'game_verified':False}
    output.parent.mkdir(parents=True,exist_ok=True);output.with_suffix('.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
    assert results,'No compatible multi-LOD or multi-material template found'
finally:document.close()
