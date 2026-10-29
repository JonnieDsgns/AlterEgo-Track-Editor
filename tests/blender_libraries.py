from pathlib import Path
import sys,json
import bpy
repo=Path(sys.argv[sys.argv.index('--')+1]).resolve();sys.path.insert(0,str(repo/'addon'))
import alterego_track_editor as addon
addon.register()
from alterego_track_editor import material_library,facility_library,marker_ui
assert bpy.ops.alterego_track.new_project(name='Library Test',code='library_test')=={'FINISHED'}
bpy.ops.mesh.primitive_cube_add();obj=bpy.context.object;obj.name='Garage Model'
# Establish real bounds, source geometry and nontrivial anchor orientation.
obj.location=(10,20,3);obj.rotation_euler.z=.5;obj.scale=(3,4,2)
bpy.context.view_layer.update()
material=bpy.data.materials.new('Surface');material.use_nodes=True;obj.data.materials.append(material)
obj['tw_project_id']=marker_ui.project(bpy.context)['tw_project_id']
assert bpy.ops.alterego_track.mark_material_template()=={'FINISHED'}
template=next(m for m in bpy.data.materials if m.get('ate_library_template'))
bpy.context.scene.ate_material_template=template.name
assert bpy.ops.alterego_track.apply_template()=={'FINISHED'}
assert obj.active_material!=template and obj.active_material.node_tree!=template.node_tree
assert not obj.active_material.get('ate_library_template')
assert bpy.ops.alterego_track.create_facility_template()=={'FINISHED'}
assembly=next(c for c in bpy.data.collections if c.get('ate_facility_template'))
bpy.context.scene.ate_facility_template=assembly.name
assert len(assembly.objects)==1 and assembly.objects[0].data==obj.data
assert max(abs(v) for v in assembly.objects[0].location)<1e-5
assert bpy.ops.alterego_track.place_facility()=={'FINISHED'}
first=bpy.context.object
assert first.instance_collection==assembly and first.get('ate_reference_only')
assert bpy.ops.alterego_track.place_facility()=={'FINISHED'}
bpy.context.view_layer.update()
assert bpy.ops.alterego_track.check_facility_overlaps()=={'FINISHED'}
root=marker_ui.project(bpy.context)
assert len(json.loads(root['ate_facility_overlaps']))==1
addon.unregister();addon.register();addon.unregister()
print('LIBRARIES_PASS: independent material instance, real geometry assembly, anchor, bounds and overlaps')
