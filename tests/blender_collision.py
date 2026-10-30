"""Native surface-only editing, source-preserving export and authored legacy output."""
from pathlib import Path
import sys,json
import bpy

repo=Path(sys.argv[sys.argv.index('--')+1]).resolve();output=Path(sys.argv[sys.argv.index('--')+2]).resolve();output.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(repo/'addon'));sys.path.insert(0,str(repo/'tests'))
import alterego_track_editor as addon
addon.register()
from test_physics_terrain import modern_fixture
from native_fixtures import make_track,pkg,erp,IDENTITY
from alterego_track_editor import jobs,native_ui,collision_ui,marker_ui
from alterego_track_editor.native_project import TrackDocument
from alterego_track_editor.physics_terrain import PhysicsTerrain

source=output/'source';archive=make_track(source);prefix='eaid://environment_package/tracks/source/wep/'
uri='eaid://environment_package/tracks/source/terrain/idf/source.idf?context=physics_terrain';layer=prefix+'collision.layer'
raw=modern_fixture()
archive.write_bytes(erp([(prefix+'source_common.wep','World',[pkg({'layers':[layer]})]),
    (layer,'WOInstances',[pkg({'instances':[{'name':'Terrain','template':'TerrainModel','uniqueid':'physics',
      'overrides':{'WorldObject':{'transform':('mat4',IDENTITY)},'PhysicsTerrain':{'terrain':uri}}}]})]),
    (uri,'TRN~',[raw]),('eaid://fixture/opaque','Unknown',[b'UNCHANGED'])]))
root,_=jobs.drain(native_ui.import_steps(bpy.context,str(source)))
terrain=next(o for o in root.all_objects if o.get('ate_native_id'))
bpy.context.view_layer.objects.active=terrain
assert bpy.ops.alterego_track.load_collision(radius=0,max_cells=500)=={'FINISHED'}
cell=bpy.context.active_object;group=collision_ui.collision_group(root,cell)
assert len(group.objects)==1
assert bpy.ops.alterego_track.load_collision(radius=0,max_cells=500)=={'FINISHED'}
assert len(group.objects)==1
assert collision_ui.surface_changes(bpy.context,group,PhysicsTerrain(raw))=={}
# Edit-mode selection must affect only the selected triangle.
bpy.ops.object.mode_set(mode='EDIT')
import bmesh
bm=bmesh.from_edit_mesh(cell.data);bm.faces.ensure_lookup_table()
for face in bm.faces:face.select=False
bm.faces[0].select=True;bpy.context.scene.ate_collision_code='RMBL'
assert bpy.ops.alterego_track.assign_collision_code()=={'FINISHED'}
bpy.ops.object.mode_set(mode='OBJECT')
assert collision_ui.surface_changes(bpy.context,group,PhysicsTerrain(raw))=={0:['RMBL','DEFA']}
assert bpy.ops.alterego_track.export_collision_surfaces(filepath=str(output/'updated'))=={'FINISHED'}
doc=TrackDocument(output/'updated');parsed=PhysicsTerrain(doc.catalog.read(uri));doc.close()
assert parsed.cells[0].codes()==['RMBL','DEFA']
check=TrackDocument(source);assert check.catalog.read(uri)==raw;check.close()
# Shared native resources must not silently choose between conflicting previews.
other=bpy.data.collections.new('Other collision binding');root.children.link(other)
for key in group.keys():other[key]=group[key]
clone=cell.copy();clone.data=cell.data.copy();other.objects.link(clone)
clone.data.materials.append(collision_ui.physical_material('GRS+'))
clone.data.polygons[0].material_index=len(clone.data.materials)-1
try:
    try:
        status=bpy.ops.alterego_track.export_collision_surfaces(filepath=str(output/'conflict'))
        assert status=={'CANCELLED'}
    except RuntimeError as exc:assert 'Conflicting' in str(exc)
    assert not (output/'conflict').exists()
finally:
    data=clone.data;bpy.data.objects.remove(clone,do_unlink=True);bpy.data.meshes.remove(data);bpy.data.collections.remove(other)
# Geometry moves cannot be passed off as safe surface updates.
cell.location.x+=1;bpy.context.view_layer.update()
try:collision_ui.surface_changes(bpy.context,group,PhysicsTerrain(raw));raise AssertionError('Moved native collision accepted')
except ValueError as exc:assert 'geometry' in str(exc).lower()
cell.location.x-=1;bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=str(output/'collision.blend'))
bpy.ops.wm.open_mainfile(filepath=str(output/'collision.blend'))
cell=next(o for o in bpy.data.objects if 'ate_collision_cell' in o);bpy.context.view_layer.objects.active=cell
assert bpy.ops.alterego_track.export_collision_surfaces(filepath=str(output/'reopened'))=={'FINISHED'}
# Authored legacy output evaluates world transforms, including mirrored parents.
for o in bpy.context.selected_objects:o.select_set(False)
mesh=bpy.data.meshes.new('Authored collision');mesh.from_pydata([(0,0,0),(2,0,0),(0,2,0)],[],[(0,1,2)])
obj=bpy.data.objects.new('Authored road',mesh);bpy.context.collection.objects.link(obj)
parent=bpy.data.objects.new('Mirrored origin',None);bpy.context.collection.objects.link(parent)
parent.location=(10,2,3);parent.scale=(-2,3,1);obj.parent=parent
obj.tw_surface.collision=True;obj.ate_physics_code='RMBL';obj.select_set(True);bpy.context.view_layer.objects.active=obj
assert bpy.ops.alterego_track.export_legacy_collision(filepath=str(output/'authored.jpak'))=={'FINISHED'}
legacy=PhysicsTerrain((output/'authored.jpak').read_bytes(),0x20002)
assert legacy.cells[0].codes()==['RMBL']
assert legacy.cells[0].positions()==[(10.,3.,-2.),(10.,3.,-8.),(6.,3.,-2.)]
addon.unregister();addon.register();addon.unregister()
result={'blender':bpy.app.version_string,'native_noop':True,'selected_face_only':True,'native_export_readback':True,
 'source_unchanged':True,'shared_conflict_rejected':True,'moved_geometry_rejected':True,'save_reopen':True,'legacy_authored_world_axes_mirror':True,'game_verified':False}
(output/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
