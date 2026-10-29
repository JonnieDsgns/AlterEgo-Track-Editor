"""Evaluated Blender topology -> native buffers, including corner UV/colour seams."""
from pathlib import Path
import sys
import json
import bpy

repo=Path(sys.argv[sys.argv.index('--')+1]).resolve()
output=Path(sys.argv[sys.argv.index('--')+2]).resolve();output.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(repo/'addon'));sys.path.insert(0,str(repo/'tests'))
import alterego_track_editor as addon
addon.register()
from test_static_geometry import static_fixture
from native_fixtures import make_track,pkg,erp,IDENTITY
from alterego_track_editor.static_geometry import StaticTemplate,write_test
from alterego_track_editor.static_geometry_ui import evaluated_input
from alterego_track_editor.native.storage import Catalog
from alterego_track_editor.native.geometry import mesh

catalog,uri=static_fixture(output/'source.erp');template=StaticTemplate(catalog,uri)
data=bpy.data.meshes.new('Authored mesh')
data.from_pydata([(0,0,0),(4,0,0),(4,0,2),(0,0,2)],[],[(0,1,2),(0,2,3)])
obj=bpy.data.objects.new('Authored static',data);bpy.context.collection.objects.link(obj)
bpy.context.view_layer.objects.active=obj;obj.select_set(True)
obj.location.x=500 # Object placement must not leak into local geometry.
for layer in range(4):
    uv=data.uv_layers.new(name='UV'+str(layer))
    for corner in data.loops:
        uv.data[corner.index].uv=(data.vertices[corner.vertex_index].co.x/4,data.vertices[corner.vertex_index].co.z/2)
# Deliberate per-corner seam at one shared position; it must survive vertex repacking.
data.uv_layers[1].data[3].uv=(.25,.75)
colour=data.color_attributes.new(name='NativeColour',type='FLOAT_COLOR',domain='CORNER')
data.color_attributes.active_color=colour
for v in colour.data:v.color=(1.,.5,0.,1.)
tri=obj.modifiers.new('Evaluated triangulation','TRIANGULATE')
bpy.context.view_layer.update()
authored=evaluated_input(bpy.context,obj,template)
assert len(authored.positions)==5 and len(authored.indices)==6
assert len(data.vertices)==4 and len(obj.modifiers)==1
assert any(row[2:]==(.25,.75) for row in authored.attributes[5,0])
assert all(row==(255,128,0,255) for row in authored.attributes[6,0])
report=write_test(catalog,uri,authored,output/'authored.erp')
check=Catalog();check.mount(output/'authored.erp');g=mesh(check,uri)
assert g.bounds==[0.,0.,0.,4.,2.,0.]
# Missing explicit layers must produce an actionable failure, not silently zero UVs.
data.uv_layers.remove(data.uv_layers[-1]);bpy.context.view_layer.update()
try:evaluated_input(bpy.context,obj,template);raise AssertionError('Missing UV layer accepted')
except ValueError as exc:assert 'UV' in str(exc)
# Exercise the actual operator from an imported project, not just the adapter.
from alterego_track_editor import native_ui,jobs
source=output/'track_source';archive=make_track(source)
static_fixture(source/'objects.erp')
prefix='eaid://environment_package/tracks/'+source.name+'/wep/'
layer=prefix+'objects.layer'
archive.write_bytes(erp([(prefix+source.name+'_common.wep','World',[pkg({'layers':[layer]})]),
    (layer,'WOInstances',[pkg({'instances':[{'name':'Board','template':'RenderModel','uniqueid':'board-test',
      'overrides':{'WorldObject':{'transform':('mat4',IDENTITY)},'Model':{'model':uri.split('?')[0]+'?context=render'}}}]})])]))
root,_=jobs.drain(native_ui.import_steps(bpy.context,str(source)))
native=next(o for o in root.all_objects if o.get('ate_native_id'))
bpy.context.view_layer.objects.active=native;native.select_set(True)
while len(native.data.uv_layers)<4:native.data.uv_layers.new(name='Explicit extra UV')
for uv in native.data.uv_layers:
    for loop in native.data.loops:
        v=native.data.vertices[loop.vertex_index].co
        uv.data[loop.index].uv=(v.x,v.z)
colour=native.data.color_attributes.new(name='Authored colour',type='FLOAT_COLOR',domain='CORNER')
native.data.color_attributes.active_color=colour
for v in colour.data:v.color=(1.,1.,1.,1.)
native.data.vertices[1].co.x=2.
assert bpy.ops.alterego_track.export_static_geometry_test(filepath=str(output/'operator.erp'))=={'FINISHED'}
operator_check=Catalog();operator_check.mount(output/'operator.erp')
assert mesh(operator_check,uri).bounds[3]==2.
addon.unregister();addon.register();addon.unregister()
result={'blender':bpy.app.version_string,'evaluated_modifier':True,'corner_seam_preserved':True,
    'source_mesh_preserved':True,'native_readback':report,'missing_uv_rejected':True,'imported_project_operator':True}
(output/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
