"""Synthetic Blender check: next-number grid slots, pit garages and garages; refusal and save/reopen."""
from pathlib import Path
import sys,json,zipfile
import bpy
from mathutils import Matrix
repo=Path(sys.argv[sys.argv.index('--')+1]).resolve()
out=Path(sys.argv[sys.argv.index('--')+2]).resolve();out.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(repo/'addon'));sys.path.insert(0,str(repo/'tests'))
from native_fixtures import make_race_track
import alterego_track_editor as addon
addon.register()
from alterego_track_editor import native_ui,jobs,marker_ui
from alterego_track_editor.native_project import TrackDocument
from alterego_track_editor.native.formats.pkg import Document,plain
source=make_race_track(out/'track');original=source.read_bytes()
root,_=jobs.drain(native_ui.import_steps(bpy.context,str(out/'track')))
named=lambda n:next(o for o in root.all_objects if o.name==n)
def add(*objects):
    for o in bpy.context.selected_objects:o.select_set(False)
    for o in objects:o.select_set(True)
    bpy.context.view_layer.objects.active=objects[0]
    return bpy.ops.alterego_track.add_race_placement()
try:add(named('base$GridSlot1'));raise AssertionError('Entry without Id accepted')
except RuntimeError as exc:assert 'not number 1' in str(exc)
assert add(named('base$F1Garage2'))=={'FINISHED'};garage=bpy.context.active_object
assert add(named('base$PitGarage4'))=={'FINISHED'};first=bpy.context.active_object
assert add(first)=={'FINISHED'};second=bpy.context.active_object  # A copy of a new placement is the next number again.
for obj,x in ((garage,140),(first,125),(second,130)):obj.matrix_world=Matrix.Translation((x,0,0))
bpy.context.scene.ate_native_view='ALL'  # Variant objects are hidden by the default F1 preview.
assert add(named('myteam$GridSlot3'))=={'FINISHED'}
assert bpy.ops.alterego_track.export_native_update(filepath=str(out/'full'/'track'),mode='FULL')=={'FINISHED'}
check=TrackDocument(out/'full'/'track')
entries={i['name']:i for r in check.layers.values() for i in plain(r['doc'].root)['instances']}
assert entries['base$F1Garage3']['overrides']['F1Garage']['left car placement']==entries['base$PitGarage5']['uniqueid']
assert entries['base$F1Garage3']['overrides']['F1Garage']['right car placement']==entries['base$PitGarage6']['uniqueid']
assert [entries[f'base$PitGarage{n}']['overrides']['WorldObject']['transform'][12] for n in (5,6)]==[125.,130.]
assert entries['myteam$GridSlot4']['overrides']['VehPlacement']['Id']==4
layers={uri:check.catalog.read(uri) for uri in check.layers};check.close()
assert bpy.ops.alterego_track.export_native_update(filepath=str(out/'update.swoftyaddon'),mode='PATCH',edit_format='PKG')=={'FINISHED'}
with zipfile.ZipFile(out/'update.swoftyaddon') as z:ops=json.loads(z.read('operations/erp.json'))['ops']
assert sum(len(o['edits']) for o in ops)==4
bpy.ops.wm.save_as_mainfile(filepath=str(out/'race.blend'));bpy.ops.wm.open_mainfile(filepath=str(out/'race.blend'))
root=marker_ui.project(bpy.context)
assert bpy.ops.alterego_track.export_native_update(filepath=str(out/'again'/'track'),mode='FULL')=={'FINISHED'}
again=TrackDocument(out/'again'/'track');assert {uri:again.catalog.read(uri) for uri in again.layers}==layers;again.close()
named=lambda n:next(o for o in root.all_objects if o.name==n)
for o in bpy.context.selected_objects:o.select_set(False)
named('base$GridSlot2').select_set(True);bpy.context.view_layer.objects.active=named('base$GridSlot2')
assert bpy.ops.alterego_track.add_race_placement()=={'FINISHED'}
try:bpy.ops.alterego_track.export_native_update(filepath=str(out/'gap'/'track'),mode='FULL');raise AssertionError('Gap accepted')
except RuntimeError as exc:assert 'numbering gap' in str(exc),exc
assert not (out/'gap').exists() and source.read_bytes()==original
addon.unregister()
result={'blender':bpy.app.version_string,'entry_without_id_refused':True,'garage_links_new_pit_garages':True,'creation_order_numbering':True,
 'variant_layer_grid_slot':True,'composable_edits':4,'save_reopen_identical':True,'gap_refused':True,'source_unchanged':True,'game_verified':False}
(out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
