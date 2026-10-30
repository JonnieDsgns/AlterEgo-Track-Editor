"""Synthetic Blender check: experimental whole-track legacy collision rebuild from native, edited preview and authored geometry."""
from pathlib import Path
import sys,json,zipfile
import bpy
from mathutils import Vector

repo=Path(sys.argv[sys.argv.index('--')+1]).resolve();output=Path(sys.argv[sys.argv.index('--')+2]).resolve();output.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(repo/'addon'));sys.path.insert(0,str(repo/'tests'))
import alterego_track_editor as addon
addon.register()
from test_physics_terrain import modern_fixture
from native_fixtures import make_track,pkg,erp,IDENTITY
from alterego_track_editor import jobs,native_ui,marker_ui
from alterego_track_editor.native_project import TrackDocument
from alterego_track_editor.physics_terrain import PhysicsTerrain,triangle_soup

source=output/'source';archive=make_track(source);prefix='eaid://environment_package/tracks/source/wep/'
uri='eaid://environment_package/tracks/source/terrain/idf/source.idf?context=physics_terrain';layer=prefix+'collision.layer'
raw=modern_fixture()
archive.write_bytes(erp([(prefix+'source_common.wep','World',[pkg({'layers':[layer]})]),
    (layer,'WOInstances',[pkg({'instances':[{'name':'Terrain','template':'TerrainModel','uniqueid':'physics',
      'overrides':{'WorldObject':{'transform':('mat4',IDENTITY)},'PhysicsTerrain':{'terrain':uri}}}]})]),
    (uri,'TRN~',[raw]),('eaid://fixture/opaque','Unknown',[b'UNCHANGED'])]))
original=archive.read_bytes()
root,_=jobs.drain(native_ui.import_steps(bpy.context,str(source)))
terrain=next(o for o in root.all_objects if o.get('ate_native_id'));bpy.context.view_layer.objects.active=terrain
assert bpy.ops.alterego_track.load_collision(radius=0,max_cells=500)=={'FINISHED'}
cell=bpy.context.active_object
cell.data.vertices[1].co+=Vector((0,0,0.5));cell.data.update()  # Blender Z = native Y
def physics(path):
    doc=TrackDocument(path);data=doc.catalog.read(uri);doc.close();return PhysicsTerrain(data)
# Without the option the main export leaves native collision untouched.
assert bpy.ops.alterego_track.export_native_update(filepath=str(output/'plain'),mode='FULL')=={'FINISHED'}
assert physics(output/'plain').data==raw
mesh=bpy.data.meshes.new('Authored kerb');mesh.from_pydata([(5,0,0),(7,0,0),(5,2,0)],[],[(0,1,2)])
kerb=bpy.data.objects.new('Authored kerb',mesh);root.objects.link(kerb)
kerb.tw_surface.collision=True;kerb.ate_physics_code='RMBL'
try:bpy.ops.alterego_track.export_native_update(filepath=str(output/'foreign'),mode='FULL',rebuild_collision=True);raise AssertionError('Foreign code accepted')
except RuntimeError as exc:assert 'not used by this track' in str(exc),exc
kerb.ate_physics_code='DEFA'
try:bpy.ops.alterego_track.export_native_update(filepath=str(output/'silent'),mode='FULL');raise AssertionError('Authored collision silently skipped')
except RuntimeError as exc:assert 'rebuild option' in str(exc),exc
assert bpy.ops.alterego_track.export_native_update(filepath=str(output/'rebuilt'),mode='FULL',rebuild_collision=True)=={'FINISHED'}
legacy=physics(output/'rebuilt');assert legacy.version==0x20002
soup=list(triangle_soup(legacy.cells));points={p for t in soup for p in t[:3]}
assert len(soup)==3 and {t[3] for t in soup}=={'DEFA'}
assert (1.0,0.5,0.0) in points and (5.0,0.0,0.0) in points and (5.0,0.0,-2.0) in points,points
assert {w for t in soup for w in t[4]}=={0xaabbccdd}  # native and per-code default words come from the base collision
report=json.loads(bpy.data.texts[root['ate_export_report']].as_string())['collision_rebuild']
assert report['authored_triangles']==1 and report['edited_cells']==[0] and report['game_verified'] is False and 'Experimental' in report['note']
check=TrackDocument(output/'rebuilt');assert check.catalog.read('eaid://fixture/opaque')==b'UNCHANGED';check.close()
assert bpy.ops.alterego_track.export_native_update(filepath=str(output/'update.swoftyaddon'),mode='PATCH',edit_format='PKG',rebuild_collision=True)=={'FINISHED'}
with zipfile.ZipFile(output/'update.swoftyaddon') as z:ops=json.loads(z.read('operations/erp.json'))['ops']
assert [o['op'] for o in ops]==['replace-resource'] and ops[0]['resource']==uri
bpy.data.objects.remove(cell,do_unlink=True)
try:bpy.ops.alterego_track.export_native_update(filepath=str(output/'removed'),mode='FULL',rebuild_collision=True);raise AssertionError('Removed preview cell accepted')
except RuntimeError as exc:assert 'removed' in str(exc),exc
assert archive.read_bytes()==original and not (output/'silent').exists() and not (output/'foreign').exists() and not (output/'removed').exists()
addon.unregister()
result={'blender':bpy.app.version_string,'default_export_keeps_native':True,'foreign_code_rejected':True,'authored_without_option_rejected':True,'edited_preview_and_authored_rebuilt':True,
 'native_vertex_words_kept':True,'update_addon_replace_resource':True,'removed_cell_rejected':True,'source_unchanged':True,'game_verified':False}
(output/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
