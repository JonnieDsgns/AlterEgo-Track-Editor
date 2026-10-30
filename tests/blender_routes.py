"""Synthetic Blender check: native route previews, linked sector edits, reload/save, full and update exports."""
from pathlib import Path
import sys,json,zipfile
import bpy
repo=Path(sys.argv[sys.argv.index('--')+1]).resolve()
out=Path(sys.argv[sys.argv.index('--')+2]).resolve();out.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(repo/'addon'));sys.path.insert(0,str(repo/'tests'))
from native_fixtures import make_route_track
import alterego_track_editor as addon
addon.register()
from alterego_track_editor import native_ui,jobs,marker_ui,route_ui
from alterego_track_editor.native_project import TrackDocument
source,tm=make_route_track(out/'track');original=source.read_bytes()
root,_=jobs.drain(native_ui.import_steps(bpy.context,str(out/'track')))
assert bpy.ops.alterego_track.load_native_routes()=={'FINISHED'}
collection=route_ui.routes_collection(root)
names=sorted(o.name for o in collection.objects)
assert 'Route maintrack' in names and 'Route pit_1' in names and 'AI track racing_line' in names,names
markers={o.name:o for o in route_ui.markers(collection)}
assert set(markers)=={'Markup sector1','Markup sector2','Markup sector3','Markup drs_activation_1','Markup pit_limiter_on'},markers
sector1=markers['Markup sector1']
for o in bpy.context.selected_objects:o.select_set(False)
sector1.select_set(True);bpy.context.view_layer.objects.active=sector1
bpy.context.scene.cursor.location=route_ui.to_blender([100,2,40])  # 140 m along the 400 m loop
assert bpy.ops.alterego_track.markup_at_cursor(side='END')=={'FINISHED'}
assert abs(sector1['ate_tm_end']-0.35)<1e-6 and abs(markers['Markup sector2']['ate_tm_start']-0.35)<1e-6
try:bpy.ops.alterego_track.markup_at_cursor(side='START');raise AssertionError('Lap start moved')
except RuntimeError as exc:assert 'lap start' in str(exc)
markers['Markup drs_activation_1']['ate_tm_start']=0.95
assert bpy.ops.alterego_track.load_native_routes()=={'FINISHED'}  # Reload keeps authored values.
collection=route_ui.routes_collection(root);markers={o.name:o for o in route_ui.markers(collection)}
assert abs(markers['Markup drs_activation_1']['ate_tm_start']-0.95)<1e-6 and abs(markers['Markup sector2']['ate_tm_start']-0.35)<1e-6
bpy.ops.wm.save_as_mainfile(filepath=str(out/'routes.blend'));bpy.ops.wm.open_mainfile(filepath=str(out/'routes.blend'))
root=marker_ui.project(bpy.context)
assert bpy.ops.alterego_track.export_native_update(filepath=str(out/'full'/'track'),mode='FULL')=={'FINISHED'}
check=TrackDocument(out/'full'/'track');rows={m['name']:(m['start'],m['end']) for m in check.routes().markup};check.close()
assert rows['sector1']==(0.0,0.35) and rows['sector2']==(0.35,0.7) and rows['drs_activation_1']==(0.95,0.1) and rows['audio_tunnel']==(0.4,0.5),rows
assert bpy.ops.alterego_track.export_native_update(filepath=str(out/'update.swoftyaddon'),mode='PATCH',edit_format='PKG')=={'FINISHED'}
with zipfile.ZipFile(out/'update.swoftyaddon') as z:ops=json.loads(z.read('operations/erp.json'))['ops']
assert [o['op'] for o in ops]==['replace-resource'] and ops[0]['resource'].endswith('.trackmarkup')
report=json.loads(bpy.data.texts[root['ate_export_report']].as_string());assert set(report['markup_edits'])=={'sector1','sector2','drs_activation_1'}
route_ui.routes_collection(root)['ate_route_tm_hash']='stale'
try:bpy.ops.alterego_track.export_native_update(filepath=str(out/'stale'/'track'),mode='FULL');raise AssertionError('Stale markup accepted')
except RuntimeError as exc:assert 'Load Native Routes' in str(exc),exc
assert not (out/'stale').exists() and source.read_bytes()==original
addon.unregister()
result={'blender':bpy.app.version_string,'route_previews':True,'linked_sector_boundary':True,'lap_start_fixed':True,'reload_keeps_edits':True,
 'save_reopen':True,'full_export_readback':True,'update_addon_replace_resource':True,'stale_source_rejected':True,'source_unchanged':True,'game_verified':False}
(out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
