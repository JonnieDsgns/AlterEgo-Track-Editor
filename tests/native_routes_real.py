"""Read-only check over every installed track folder: BXML byte-exact round trips and markup edit readback.

Arguments: tracks folder (…/environment_package/tracks), output JSON. Private summary output only.
"""
from pathlib import Path
import collections,json,sys,time,types

repo=Path(__file__).resolve().parents[1]
package=types.ModuleType('alterego_track_editor');package.__path__=[str(repo/'addon/alterego_track_editor')];sys.modules['alterego_track_editor']=package
from alterego_track_editor.native.storage import Catalog
from alterego_track_editor.native.formats.bxml import Document
from alterego_track_editor.native_routes import RouteData

base,output=map(Path,sys.argv[1:3]);start=time.perf_counter();codec=collections.Counter();tracks=[]
for folder in sorted(p for p in base.iterdir() if p.is_dir() and (p/'wep').is_dir()):
    catalog=Catalog()
    for archive in sorted((folder/'wep').glob('*.erp')):catalog.mount(archive)
    for uri,(_,resource) in catalog.by_uri.items():
        for i in range(len(resource.fragments)):
            raw=catalog.read(uri,i)
            if raw[1:5]==b'BXML':
                assert Document(raw).to_bytes()==raw,uri
                codec[resource.type_name]+=1
    try:routes=RouteData(catalog,folder.name)
    except ValueError as exc:
        tracks.append({'track':folder.name,'routes':None,'reason':str(exc)});continue
    assert routes.write_markup({})==routes.tm_raw
    sectors={t:m for m in routes.markup for t in m['types'] if t.startswith('sector_')};edits={}
    if len(sectors)==3:
        boundary=round((sectors['sector_1']['end']+sectors['sector_2']['end'])/2,4)
        edits[sectors['sector_1']['index']]=(sectors['sector_1']['start'],boundary);edits[sectors['sector_2']['index']]=(boundary,sectors['sector_2']['end'])
    drs=next((m for m in routes.markup if 'drs_act' in m['types']),None)
    if drs:edits[drs['index']]=((drs['start']+0.001)%1,drs['end'])
    edited=routes.write_markup(edits)  # verifies that only the edited attributes changed
    tracks.append({'track':folder.name,'markup':len(routes.markup),'gameplay':sum(m['gameplay'] for m in routes.markup),
        'edits':len(edits),'main_length_m':round(routes.splines['maintrack'].length,1),'ai_gates':len(routes.ai['gates']) if routes.ai else 0,
        'edited_bytes':len(edited)})
result={'bxml_round_trips':dict(codec),'tracks':tracks,'seconds':round(time.perf_counter()-start,1),'game_verified':False}
output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2))
print(json.dumps({'bxml_round_trips':dict(codec),'tracks_with_routes':sum(1 for t in tracks if t.get('markup')),'without':[t['track'] for t in tracks if not t.get('markup')]}))
