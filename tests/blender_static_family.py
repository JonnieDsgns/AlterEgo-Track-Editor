"""Actual native LOD loading, material-slot export, preview and reuse regression."""
from pathlib import Path
import sys,json
import bpy

repo=Path(sys.argv[sys.argv.index('--')+1]).resolve()
output=Path(sys.argv[sys.argv.index('--')+2]).resolve();output.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(repo/'addon'));sys.path.insert(0,str(repo/'tests'))
import alterego_track_editor as addon
addon.register()
from test_static_family import family_fixture
from native_fixtures import make_track,pkg,erp,IDENTITY
from alterego_track_editor import native_ui,jobs,static_geometry_ui
from alterego_track_editor.native_project import TrackDocument
from alterego_track_editor.native.storage import Catalog
from alterego_track_editor.native.geometry import mesh

source=output/'source';archive=make_track(source);_,family=family_fixture(source/'objects.erp')
prefix='eaid://environment_package/tracks/'+source.name+'/wep/';layer=prefix+'objects.layer'
archive.write_bytes(erp([(prefix+source.name+'_common.wep','World',[pkg({'layers':[layer]})]),
    (layer,'WOInstances',[pkg({'instances':[{'name':'Board','template':'RenderModel','uniqueid':'family-test',
     'overrides':{'WorldObject':{'transform':('mat4',IDENTITY)},'Model':{'model':family+'?context=render'}}}]})])]))
root,_=jobs.drain(native_ui.import_steps(bpy.context,str(source)))
native=next(o for o in root.all_objects if o.get('ate_native_id'))
bpy.context.view_layer.objects.active=native;native.select_set(True)
original_mesh=native.data;original_vertices=[tuple(v.co) for v in native.data.vertices]
assert bpy.ops.alterego_track.load_geometry_lods()=={'FINISHED'}
group=static_geometry_ui.geometry_group(root,bpy.context.active_object)
assert len(group.objects)==2
assert [o.ate_geometry_lod for o in group.objects if not o.hide_get()]==[0]
assert all(len(o.data.uv_layers)==4 for o in group.objects)
assert bpy.ops.alterego_track.load_geometry_lods()=={'FINISHED'}
assert len(group.objects)==2 # Never discard edits or create another family on repeated load.
for obj in group.objects:
    for vertex in obj.data.vertices:vertex.co.x+=obj.ate_geometry_lod*20
    for uv in obj.data.uv_layers:
        for loop in obj.data.loops:
            v=obj.data.vertices[loop.vertex_index].co;uv.data[loop.index].uv=(v.x,v.z)
    # Distinguish two material submeshes spatially and preserve their corner data.
    for face in obj.data.polygons:
        if face.material_index==1:
            for i in face.vertices:obj.data.vertices[i].co.x+=10
    obj.data.update()
assert bpy.ops.alterego_track.preview_geometry_lod(level=1)=={'FINISHED'}
assert bpy.context.active_object.ate_geometry_lod==1
assert [o.ate_geometry_lod for o in group.objects if not o.hide_get()]==[1]
# Hidden detail levels must still participate in complete family export.
assert bpy.ops.alterego_track.export_static_geometry_test(filepath=str(output/'family.erp'))=={'FINISHED'}
check=Catalog();check.mount(output/'family.erp')
for lod in range(2):
    g=mesh(check,family+f'?lod={lod}&mesh')
    assert [r['slot'] for r in g.groups]==['Surface','Fence']
    assert g.bounds==[lod*20.,0.,0.,lod*20.+11.,1.,0.]
assert native.data==original_mesh and [tuple(v.co) for v in native.data.vertices]==original_vertices
missing=next(o for o in group.objects if o.ate_geometry_lod==0)
group.objects.unlink(missing)
try:
    try:
        status=bpy.ops.alterego_track.export_static_geometry_test(filepath=str(output/'incomplete.erp'))
        assert status=={'CANCELLED'}
    except RuntimeError as exc:assert 'LOD family incomplete' in str(exc)
    assert not (output/'incomplete.erp').exists()
finally:group.objects.link(missing)
document=TrackDocument(source)
assert native_ui.collect_changes(root,document)=={} # Authoring references do not edit original placements.
document.close()
# Save/reopen preserves association and hidden LODs.
bpy.ops.wm.save_as_mainfile(filepath=str(output/'family.blend'))
bpy.ops.wm.open_mainfile(filepath=str(output/'family.blend'))
obj=next(o for o in bpy.data.objects if o.get('ate_geometry_source_id') and o.ate_geometry_lod==0)
bpy.context.view_layer.objects.active=obj
assert bpy.ops.alterego_track.export_static_geometry_test(filepath=str(output/'reopened.erp'))=={'FINISHED'}
result={'blender':bpy.app.version_string,'native_lod_loading':True,'idempotent_reuse':True,
 'multi_material_readback':True,'hidden_lods_exported':True,'incomplete_lod_rejected':True,'original_unchanged':True,'save_reopen':True,'game_verified':False}
(output/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
addon.unregister()
