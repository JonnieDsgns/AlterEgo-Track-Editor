"""Bounded real check: native route previews and markup edits on a stock track; changes-only output, private."""
from pathlib import Path
import sys,json,time,zipfile
import bpy
args=sys.argv[sys.argv.index('--')+1:]
repo=Path(args[0]).resolve();source=args[1];output=Path(args[2]).resolve();output.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(repo/'addon'))
import alterego_track_editor as addon
addon.register()
from alterego_track_editor import native_ui,jobs,route_ui
from alterego_track_editor.native.formats.bxml import Document
RealDocument=native_ui.TrackDocument
class SampleDocument(RealDocument):
    def __init__(self,*a,**k):
        super().__init__(*a,**k);self.records=[r for r in self.records if not r['clone_reason']][:4];self.by_id={r['id']:r for r in self.records}
native_ui.TrackDocument=SampleDocument
start=time.perf_counter();root,_=jobs.drain(native_ui.import_steps(bpy.context,source))
assert bpy.ops.alterego_track.load_native_routes()=={'FINISHED'};loaded=time.perf_counter()-start
collection=route_ui.routes_collection(root);markers={o.name:o for o in route_ui.markers(collection)}
drs=next(o for n,o in markers.items() if 'drs_act' in json.loads(o['ate_tm_types']))
sector2=next(o for o in markers.values() if 'sector_2' in json.loads(o['ate_tm_types']))
old_drs=drs['ate_tm_start'];drs['ate_tm_start']=round((old_drs+0.002)%1,6)
for o in bpy.context.selected_objects:o.select_set(False)
sector2.select_set(True);bpy.context.view_layer.objects.active=sector2
spline=route_ui.stored_spline(collection,'maintrack');boundary=round(sector2['ate_tm_start']+0.01,6)
bpy.context.scene.cursor.location=route_ui.to_blender(spline.point(boundary))
assert bpy.ops.alterego_track.markup_at_cursor(side='START')=={'FINISHED'}
assert abs(sector2['ate_tm_start']-boundary)<2e-4,(sector2['ate_tm_start'],boundary)
target=output/'markup.swoftyaddon'
assert bpy.ops.alterego_track.export_native_update(filepath=str(target),mode='PATCH',edit_format='PKG')=={'FINISHED'}
with zipfile.ZipFile(target) as z:
    ops=json.loads(z.read('operations/erp.json'))['ops'];tm=Document(z.read(ops[0]['source']))
rows={e.get('Name'):(e.get('Start'),e.get('End')) for e in tm.root.elements('MarkupList')[0].elements('MarkupElement')}
report=json.loads(bpy.data.texts[root['ate_export_report']].as_string())
addon.unregister()
result={'scope':'real stock track routes/markup in Blender; 4 sample placements; changes-only addon only','blender':bpy.app.version_string,
 'route_objects':len(collection.objects),'editable_intervals':len(markers),'load_seconds':round(loaded,2),'ops':[o['op'] for o in ops],
 'edited':report['markup_edits'],'game_verified':False}
result['edited_rows']={k:rows[k] for k in report['markup_edits']}
(output/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
