"""Synthetic Blender check: deleting static props, PVS opt-in, functional refusal and whole-layer exports."""
from pathlib import Path
import sys,json,zipfile
import bpy
repo=Path(sys.argv[sys.argv.index('--')+1]).resolve()
out=Path(sys.argv[sys.argv.index('--')+2]).resolve();out.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(repo/'addon'));sys.path.insert(0,str(repo/'tests'))
from native_fixtures import make_reference_track
import alterego_track_editor as addon
addon.register()
from alterego_track_editor import native_ui,jobs
from alterego_track_editor.native_project import TrackDocument
source=make_reference_track(out/'track');original=source.read_bytes()
root,_=jobs.drain(native_ui.import_steps(bpy.context,str(out/'track')))
named=lambda n:next(o for o in root.all_objects if o.name==n)
bpy.data.objects.remove(named('objects$spare_a'),do_unlink=True)
assert bpy.ops.alterego_track.export_native_update(filepath=str(out/'one'/'track'),mode='FULL')=={'FINISHED'}
check=TrackDocument(out/'one'/'track');assert sorted(r['name'] for r in check.records)==['objects$barrier_a','objects$board_a'];check.close()
try:bpy.ops.alterego_track.export_native_update(filepath=str(out/'pkg.zip'),mode='PATCH',edit_format='PKG');raise AssertionError('Composable deletion accepted')
except RuntimeError as exc:assert 'Whole Layers' in str(exc),exc
assert bpy.ops.alterego_track.export_native_update(filepath=str(out/'whole.zip'),mode='PATCH',edit_format='REPLACE')=={'FINISHED'}
with zipfile.ZipFile(out/'whole.zip') as z:assert len(json.loads(z.read('provenance.json'))['deleted_placements'])==1
bpy.data.objects.remove(named('objects$barrier_a'),do_unlink=True)
try:bpy.ops.alterego_track.export_native_update(filepath=str(out/'blocked'/'track'),mode='FULL');raise AssertionError('PVS deletion accepted')
except RuntimeError as exc:assert 'precomputed visibility' in str(exc),exc
assert bpy.ops.alterego_track.export_native_update(filepath=str(out/'two'/'track'),mode='FULL',allow_pvs_deletions=True)=={'FINISHED'}
report=json.loads(bpy.data.texts[root['ate_export_report']].as_string())
assert sorted((d['name'],d['pvs_listed']) for d in report['deleted_placements'])==[('objects$barrier_a',True),('objects$spare_a',False)]
bpy.data.objects.remove(named('objects$board_a'),do_unlink=True)
try:bpy.ops.alterego_track.export_native_update(filepath=str(out/'ref'/'track'),mode='FULL',allow_pvs_deletions=True);raise AssertionError('Referenced deletion accepted')
except RuntimeError as exc:assert 'reference' in str(exc),exc
assert not (out/'blocked').exists() and not (out/'ref').exists() and source.read_bytes()==original
addon.unregister()
result={'blender':bpy.app.version_string,'static_prop_deleted':True,'composable_refused':True,'whole_layer_update':True,
 'pvs_opt_in_required':True,'referenced_refused':True,'source_unchanged':True,'game_verified':False}
(out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
