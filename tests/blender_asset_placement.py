"""Synthetic Blender check: edited LOD family placed as a new native object, full/update export, save/reopen."""
from pathlib import Path
import sys,json,zipfile
import bpy
repo=Path(sys.argv[sys.argv.index('--')+1]).resolve()
output=Path(sys.argv[sys.argv.index('--')+2]).resolve();output.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(repo/'addon'));sys.path.insert(0,str(repo/'tests'))
import alterego_track_editor as addon
addon.register()
from test_native_asset_placement import canonical_source
from alterego_track_editor import native_ui,jobs,static_geometry_ui,marker_ui
from alterego_track_editor.native_project import TrackDocument
from alterego_track_editor.native.geometry import mesh
from alterego_track_editor.native.storage import Catalog

(output/'source-root').mkdir();source,family,binding=canonical_source(output/'source-root');original=(source/'wep/input_common.erp').read_bytes()
root,_=jobs.drain(native_ui.import_steps(bpy.context,str(source)))
native=next(o for o in root.all_objects if o.get('ate_native_id'))
bpy.context.view_layer.objects.active=native;native.select_set(True)
assert bpy.ops.alterego_track.load_geometry_lods()=={'FINISHED'}
group=static_geometry_ui.geometry_group(root,bpy.context.active_object)
for obj in group.objects:
    for vertex in obj.data.vertices:vertex.co.z+=2+obj.ate_geometry_lod
    obj.data.update()
try:bpy.ops.alterego_track.place_edited_asset(asset_name='Bad Name');raise AssertionError('Invalid asset name accepted')
except RuntimeError as exc:assert 'lowercase' in str(exc)
bpy.context.scene.cursor.location=(50,0,0)
assert bpy.ops.alterego_track.place_edited_asset(asset_name='tall_board')=={'FINISHED'}
placed=bpy.context.active_object
assert placed.data in {o.data for o in group.objects} and placed['ate_asset_name']=='tall_board'
assert bpy.ops.alterego_track.export_native_update(filepath=str(output/'out'/'input'),mode='FULL')=={'FINISHED'}
check=TrackDocument(output/'out'/'input');new=next(r for r in check.records if r['name'].startswith('objects$tall_board_ate_'))
target='eaid://environment_package/tracks/input/objects/tall_board.idf'
assert new['model']==target+'?context=render' and abs(new['world'][12]+new['render'][12]-50)<1e-5 and new['render_error'] is None,(new['model'],new['world'],new['render_error'])
# Native y is Blender z: every LOD carries its own authored lift.
for lod in range(2):
    bounds=mesh(check.catalog,target+f'?lod={lod}&mesh').bounds;assert abs(bounds[1]-(2+lod))<1e-5,bounds
assert next(r for r in check.records if r['name']=='objects$board_a')['model']==family+'?context=render'
layer=check.catalog.read(new['layer']);family_bytes=check.catalog.read(target+'?lod=0&mesh');check.close()
assert bpy.ops.alterego_track.export_native_update(filepath=str(output/'update.swoftyaddon'),mode='PATCH',edit_format='PKG')=={'FINISHED'}
with zipfile.ZipFile(output/'update.swoftyaddon') as z:
    ops=json.loads(z.read('operations/erp.json'))['ops'];(output/'shipped.erp').write_bytes(z.read('assets/new-assets.erp'))
assert [o['op'] for o in ops][-1]=='patch-pkg' and sum(o['op']=='copy-resource' for o in ops)>=8
shipped=Catalog();shipped.mount(output/'shipped.erp');assert shipped.read(target+'?lod=0&mesh')==family_bytes
report=json.loads(bpy.data.texts[root['ate_export_report']].as_string());assert 'tall_board' in report['new_assets']

bpy.ops.wm.save_as_mainfile(filepath=str(output/'asset.blend'))
bpy.ops.wm.open_mainfile(filepath=str(output/'asset.blend'))
root=marker_ui.project(bpy.context)
assert bpy.ops.alterego_track.export_native_update(filepath=str(output/'again'/'input'),mode='FULL')=={'FINISHED'}
again=TrackDocument(output/'again'/'input')
assert again.catalog.read(new['layer'])==layer and again.catalog.read(target+'?lod=0&mesh')==family_bytes
again.close()
# Existing prop uses the edited family; restoring it removes the replacement again.
group=next(c for c in root.children if c.get('ate_geometry_source_id'))
native=next(o for o in root.all_objects if o.get('ate_native_id'))
for o in bpy.context.selected_objects:o.select_set(False)
native.select_set(True);lod=min(group.objects,key=lambda o:o.ate_geometry_lod);lod.select_set(True);bpy.context.view_layer.objects.active=lod
assert bpy.ops.alterego_track.use_edited_asset(asset_name='tall_board')=={'FINISHED'} and native.data==lod.data
assert bpy.ops.alterego_track.export_native_update(filepath=str(output/'replaced'/'input'),mode='FULL')=={'FINISHED'}
replaced=TrackDocument(output/'replaced'/'input');board=next(r for r in replaced.records if r['name']=='objects$board_a')
assert board['model']==target+'?context=render' and sum(r['model']==target+'?context=render' for r in replaced.records)==2
replaced.close()
for o in bpy.context.selected_objects:o.select_set(False)
native.select_set(True);bpy.context.view_layer.objects.active=native
assert bpy.ops.alterego_track.restore_original_model()=={'FINISHED'} and 'ate_asset_source' not in native
retargets=[];doc=TrackDocument(source);native_ui.collect_changes(root,doc,[],[],retargets);doc.close();assert retargets==[]
# Without its loaded LOD family the placement cannot silently export the source model.
group=next(c for c in root.children if c.get('ate_geometry_source_id'))
for obj in list(group.objects):
    if obj.get('ate_asset_name') is None:group.objects.unlink(obj)
try:bpy.ops.alterego_track.export_native_update(filepath=str(output/'invalid'/'input'),mode='FULL');raise AssertionError('Missing family accepted')
except RuntimeError as exc:assert 'geometry LODs' in str(exc),exc
assert not (output/'invalid').exists() and (source/'wep/input_common.erp').read_bytes()==original
addon.unregister()
result={'blender':bpy.app.version_string,'invalid_name_rejected':True,'shared_lod_mesh':True,'full_export_new_family':True,
 'per_lod_edits':True,'existing_prop_replaced_and_restored':True,'update_addon_copy_resource':True,'save_reopen_identical':True,'missing_family_rejected':True,
 'source_unchanged':True,'game_verified':False}
(output/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
