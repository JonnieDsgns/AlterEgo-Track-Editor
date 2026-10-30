"""Read-only real check of numbered race placements (grid slots, pit garages, garages, pit boxes); private JSON output.

Arguments: native track folder, output JSON, optional SwoftyLauncher checkout for a serializer comparison.
"""
from pathlib import Path
import copy,importlib.util,json,sys,time,types

repo=Path(__file__).resolve().parents[1]
package=types.ModuleType('alterego_track_editor');package.__path__=[str(repo/'addon/alterego_track_editor')];sys.modules['alterego_track_editor']=package
from alterego_track_editor.native_project import TrackDocument,RACE_NAME
from alterego_track_editor.native.formats.pkg import Document,plain

source,output=map(Path,sys.argv[1:3]);swofty=Path(sys.argv[3]) if len(sys.argv)>3 else None
start=time.perf_counter();doc=TrackDocument(source)
try:
    def top(kind,layer=None):
        rows=[(int(RACE_NAME.fullmatch(r['name']).group(3)),r) for r in doc.records
              if RACE_NAME.fullmatch(r['name']) and RACE_NAME.fullmatch(r['name']).group(2)==kind and (layer is None or r['layer']==layer)]
        return max(rows,key=lambda x:x[0])[1]
    slot=top('GridSlot');layer=slot['layer']
    specs=[{'id':'%032x'%i,'source':top(kind,layer)['id'],'world':top(kind,layer)['world'],'race':True,'order':i}
           for i,kind in enumerate(('PitGarage','PitGarage','F1Garage','PitBox','GridSlot','GridSlot'))]
    replacements=doc.apply({},specs);data=replacements[layer]
    entries={i['name']:i for i in plain(Document(data).root)['instances']}
    added=[i['name'] for i in doc.inserted]
    garage=entries[next(n for n in added if 'F1Garage' in n)]['overrides']['F1Garage']
    pits=[entries[n]['uniqueid'] for n in added if 'PitGarage' in n]
    assert [garage['left car placement'],garage['right car placement']]==pits
    base=top('GridSlot',next(r['layer'] for r in doc.records if r['name'].endswith('GridSlot2')))
    try:
        doc.apply({},[{'id':'f'*32,'source':base['id'],'world':base['world'],'race':True}]);gap=None
    except ValueError as exc:gap=str(exc)
    result={'track':source.name,'layer':layer,'variants':slot['variants'],'added':added,'garage_links_new_pit_garages':True,
        'base_layer_refusal':gap,'game_verified':False}
    doc.apply({},specs);result['composable_edits']=len(doc.layer_edits[layer])
    if swofty:
        spec=importlib.util.spec_from_file_location('swofty_pkg',swofty/'tools/pkg.py');sw=importlib.util.module_from_spec(spec);spec.loader.exec_module(sw)
        pkg=sw.Pkg(doc.layers[layer]['doc'].data);items=pkg.root['instances'].items
        find=lambda name:next(e for e in items if e['name'].value==name)
        for row in doc.inserted:
            want=entries[row['name']];clone=copy.deepcopy(find(row['source']))
            clone.set('name',sw.Val('stri',row['name']));clone.set('uniqueid',sw.Val('woid',row['uniqueid']))
            clone['overrides']['WorldObject'].set('transform',sw.Val('mat4',want['overrides']['WorldObject']['transform']))
            component='F1Garage' if 'F1Garage' in want['overrides'] else 'VehPlacement'
            for key,value in want['overrides'][component].items():
                old=clone['overrides'][component][key]
                if old.type in ('ui32','si32','woid'):clone['overrides'][component].set(key,sw.Val(old.type,value))
            items.append(clone)
        result['swofty_python_serializer_exact']=pkg.to_bytes()==data
        assert result['swofty_python_serializer_exact']
    result['seconds']=round(time.perf_counter()-start,2)
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2));print(json.dumps(result))
finally:doc.close()
