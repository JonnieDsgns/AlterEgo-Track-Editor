"""Synthetic Blender check: explicit native duplicates, rejection rules, full/composable export and save/reopen."""
from pathlib import Path
import sys,json,zipfile
import bpy
from mathutils import Matrix
repo=Path(sys.argv[sys.argv.index('--')+1]).resolve()
out=Path(sys.argv[sys.argv.index('--')+2]).resolve();out.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(repo/'addon'));sys.path.insert(0,str(repo/'tests'))
from native_fixtures import make_canonical_track
import alterego_track_editor as addon
addon.register()
from alterego_track_editor import native_ui,jobs,marker_ui
from alterego_track_editor.native_project import TrackDocument
folder=out/'synthetic';source,_=make_canonical_track(folder,mirror=True);original=source.read_bytes()
root,warnings=jobs.drain(native_ui.import_steps(bpy.context,str(folder)))
named=lambda prefix:next(o for o in root.all_objects if o.name.startswith(prefix))
barrier,grid=named('objects$barrier_a'),named('objects$GridSlot1')
assert barrier['ate_native_cloneable'] and not grid['ate_native_cloneable']

def select(*objects):
    for o in bpy.context.selected_objects:o.select_set(False)
    for o in objects:o.select_set(True)
    bpy.context.view_layer.objects.active=objects[0]

select(grid)
try:bpy.ops.alterego_track.duplicate_native_placement();raise AssertionError('Functional duplicate accepted')
except RuntimeError as exc:assert 'static props' in str(exc)
before=len(bpy.data.objects);select(barrier)
assert bpy.ops.alterego_track.duplicate_native_placement()=={'FINISHED'}
assert len(bpy.data.objects)==before+1
clone=bpy.context.active_object
assert clone is not barrier and clone.data is barrier.data and 'ate_native_id' not in clone
assert clone['ate_native_clone_of']==barrier['ate_native_id'] and set(clone.users_collection)==set(barrier.users_collection)
clone.matrix_world=Matrix.Translation((10,0,0))@clone.matrix_world
bpy.context.view_layer.update()

doc=TrackDocument(folder)
try:native_ui.collect_changes(root,doc);raise AssertionError('Insertion accepted by placement-only caller')
except ValueError as exc:assert 'Export Updated Native Track' in str(exc)
insertions=[];assert native_ui.collect_changes(root,doc,insertions)=={} and len(insertions)==1
assert abs(insertions[0]['world'][12]-15)<1e-5
# Plain copies are not silent insertions.
for copied in (barrier.copy(),clone.copy()):
    for c in barrier.users_collection:c.objects.link(copied)
    try:native_ui.collect_changes(root,TrackDocument(folder),[]);raise AssertionError('Plain copy accepted')
    except ValueError as exc:assert 'Duplicate as New Placement' in str(exc),exc
    bpy.data.objects.remove(copied,do_unlink=True)

assert bpy.ops.alterego_track.export_native_update(filepath=str(out/'full'),mode='FULL')=={'FINISHED'}
check=TrackDocument(out/'full');new=[r for r in check.records if r['name'].startswith('objects$barrier_a_ate_')]
assert len(check.records)==4 and len(new)==1 and abs(new[0]['world'][12]-15)<1e-5
layer=check.catalog.read(new[0]['layer']);check.close()
assert bpy.ops.alterego_track.export_native_update(filepath=str(out/'update.swoftyaddon'),mode='PATCH',edit_format='PKG')=={'FINISHED'}
with zipfile.ZipFile(out/'update.swoftyaddon') as z:ops=json.loads(z.read('operations/erp.json'))['ops']
assert len(ops)==2 and {o['op'] for o in ops}=={'patch-pkg'} and ops[0]['edits'][0]['op']=='clone-entry'
report=json.loads(bpy.data.texts[root['ate_export_report']].as_string())
assert len(report['inserted_placements'])==1 and 'no collision' in report['limitations'] and report['game_verified'] is False

bpy.ops.wm.save_as_mainfile(filepath=str(out/'insertion.blend'))
bpy.ops.wm.open_mainfile(filepath=str(out/'insertion.blend'))
root=marker_ui.project(bpy.context)
assert bpy.ops.alterego_track.export_native_update(filepath=str(out/'reopened'),mode='FULL')=={'FINISHED'}
again=TrackDocument(out/'reopened');uri=next(r['layer'] for r in again.records)
assert again.catalog.read(uri)==layer,'Persisted new placement identity changed after save/reopen'
again.close()
assert source.read_bytes()==original
addon.unregister()
result={'blender':bpy.app.version_string,'functional_duplicate_refused':True,'shared_mesh_duplicate':True,
 'plain_copies_rejected':True,'full_export_readback':True,'composable_patch_ops':len(ops),'save_reopen_identical_layer':True,
 'source_unchanged':True,'game_verified':False}
(out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
