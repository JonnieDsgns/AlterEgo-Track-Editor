"""Synthetic Blender regression for the foundation; writes only an explicit build folder."""
import json
from pathlib import Path
import sys
import bpy
from mathutils import Matrix
args=sys.argv[sys.argv.index('--')+1:]
repo=Path(args[0]).resolve();out=Path(args[1]).resolve();out.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(repo/'addon'))
import alterego_track_editor as addon
addon.register()
from alterego_track_editor import assets,collection_layout,marker_ui,project_ui
assert addon.bl_info['blender']==(4,5,0)
assert bpy.ops.track_workshop.open_workspace()=={'FINISHED'}
workspace=next(w for w in bpy.data.workspaces if w.get("tw_workspace"))
assert workspace.name=='AlterEgo Track Editor'
count=len(bpy.data.workspaces)
assert bpy.ops.track_workshop.open_workspace()=={'FINISHED'}
assert len(bpy.data.workspaces)==count
assert bpy.ops.alterego_track.new_project(name='Foundation Test',code='foundation')=={'FINISHED'}
root=marker_ui.project(bpy.context);identity=root['tw_project_id'];cols=collection_layout.ensure(root)
mesh=bpy.data.meshes.new('Shared Geometry');mesh.from_pydata([(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)])
mat=bpy.data.materials.new('Shared Material');mesh.materials.append(mat)
a=bpy.data.objects.new('Asset',mesh);b=bpy.data.objects.new('Sibling',mesh)
cols['SOURCE'].objects.link(a);cols['SOURCE'].objects.link(b)
unrelated=bpy.data.collections.new('Unrelated');bpy.context.scene.collection.children.link(unrelated);unrelated.objects.link(a)
parent=bpy.data.objects.new('Source Parent',None);cols['SOURCE'].objects.link(parent)
parent.matrix_world=Matrix.Translation((7,8,9))@Matrix.Diagonal((-1,2,3,1))
a.parent=parent;a.matrix_basis=Matrix.Translation((2,3,4))
bpy.context.view_layer.update();pose=a.matrix_world.copy()
counts=(len(bpy.data.objects),len(bpy.data.meshes),len(bpy.data.materials))
bpy.ops.object.select_all(action='DESELECT');a.select_set(True);bpy.context.view_layer.objects.active=a
bpy.context.scene.tw_asset_target='COMMON_OBJECTS'
bpy.context.preferences.edit.use_global_undo=True
bpy.ops.ed.undo_push(message='Before Assignment')
assert bpy.ops.track_workshop.asset_assign()=={'FINISHED'}
bpy.ops.ed.undo_push(message='After Assignment')
assert a.name in cols['COMMON_OBJECTS'].objects and a.name not in cols['SOURCE'].objects
assert a.data==b.data==mesh and a.material_slots[0].material==mat
assert a.name in unrelated.objects
asset_id=a['tw_asset_id']
assert (len(bpy.data.objects),len(bpy.data.meshes),len(bpy.data.materials))==counts
assert max(abs(a.matrix_world[i][j]-pose[i][j]) for i in range(4) for j in range(4))<1e-5
# Undo recreates Blender references: reacquire all datablocks afterwards.
assert bpy.ops.ed.undo()=={'FINISHED'}
a=bpy.data.objects['Asset'];root=next(c for c in bpy.data.collections if c.get('tw_project_id')==identity);cols=collection_layout.ensure(root)
assert a.name in cols['SOURCE'].objects and not a.get('tw_asset_id')
assert bpy.ops.ed.redo()=={'FINISHED'}
a=bpy.data.objects['Asset'];b=bpy.data.objects['Sibling'];root=next(c for c in bpy.data.collections if c.get('tw_project_id')==identity);cols=collection_layout.ensure(root)
assert a.name in cols['COMMON_OBJECTS'].objects
# Automatic terrain moves the exact object and is idempotent.
b['tw_source_id']='synthetic-terrain';b['tw_surface_status']='SUGGESTED';b.tw_surface.collision=True;b.tw_surface.surface='ASPHALT'
counts=(len(bpy.data.objects),len(bpy.data.meshes),len(bpy.data.materials))
assert assets.prepare_terrain(bpy.context,root,cols)==[b]
assert assets.prepare_terrain(bpy.context,root,cols)==[]
assert b.name in cols['COMMON_TERRAIN'].objects and b.data==a.data
assert (len(bpy.data.objects),len(bpy.data.meshes),len(bpy.data.materials))==counts
source=out/'synthetic-source.txt';source.write_text('original')
assert bpy.ops.alterego_track.add_source(filepath=str(source))=={'FINISHED'}
assert bpy.ops.alterego_track.create_companion(directory=str(out/'companion'))=={'FINISHED'}
assert (out/'companion/project.json').is_file()
blend=out/'foundation.blend';bpy.ops.wm.save_as_mainfile(filepath=str(blend))
bpy.ops.wm.open_mainfile(filepath=str(blend))
root=next(c for c in bpy.data.collections if c.get('tw_project_id')==identity)
assert root['ate_track_code']=='foundation'
a=bpy.data.objects['Asset'];b=bpy.data.objects['Sibling'];cols=collection_layout.ensure(root)
assert a['tw_asset_id']==asset_id
assert a.data==b.data and a.name in cols['COMMON_OBJECTS'].objects and b.name in cols['COMMON_TERRAIN'].objects
assert max(abs(a.matrix_world[i][j]-pose[i][j]) for i in range(4) for j in range(4))<1e-5
source.write_text('changed')
assert bpy.ops.alterego_track.check_sources()=={'FINISHED'}
assert json.loads(root['ate_source_findings'])[0]['status']=='CHANGED'
assert bpy.ops.alterego_track.create_companion(directory=str(out/'companion'))=={'FINISHED'}
# Registration lifecycle with authored data present.
addon.unregister();assert not hasattr(bpy.types.Scene,'tw_asset_target')
addon.register();addon.unregister()
result={'blender':bpy.app.version_string,'manual_move':True,'automatic_terrain_move':True,'sharing':True,'transforms':True,'undo_redo':True,'save_reopen':True,'source_change_detection':True,'companion_manifest':True,'registration':True,'scope':'synthetic headless Blender; no native/game export'}
(out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
