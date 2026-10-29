"""Bounded real native model -> Blender LODs -> full-family ERP readback."""
from pathlib import Path
import sys,json,time
import struct
import bpy

args=sys.argv[sys.argv.index('--')+1:]
repo=Path(args[0]).resolve();source=args[1];output=Path(args[2]).resolve()
sys.path.insert(0,str(repo/'addon'))
import alterego_track_editor as addon
addon.register()
from alterego_track_editor import native_ui,jobs,static_geometry_ui
from alterego_track_editor.native.storage import Catalog
from alterego_track_editor.native.geometry import mesh
RealDocument=native_ui.TrackDocument
family='eaid://environment_package/core_assets/objects/idf/barriers/armco_monaco_white_b.idf'
class SampleDocument(RealDocument):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.records=[r for r in self.records if r['model']==family+'?context=render' and not r['render_error']][:1]
        assert len(self.records)==1,'Target template has no supported placed instance'
        self.by_id={r['id']:r for r in self.records}
native_ui.TrackDocument=SampleDocument
start=time.perf_counter()
root,warnings=jobs.drain(native_ui.import_steps(bpy.context,source))
native=next(o for o in root.all_objects if o.get('ate_native_id'))
bpy.context.view_layer.objects.active=native;native.select_set(True)
assert bpy.ops.alterego_track.load_geometry_lods()=={'FINISHED'}
group=static_geometry_ui.geometry_group(root,bpy.context.active_object)
assert len(group.objects)==3
# A small authored deformation; original native object remains untouched.
target=bpy.context.active_object;target.data.vertices[0].co.x+=.01
assert bpy.ops.alterego_track.export_static_geometry_test(filepath=str(output))=={'FINISHED'}
check=Catalog();check.mount(output)
counts=[mesh(check,family+f'?lod={i}&mesh').triangles for i in range(3)]
document=RealDocument(source)
before=struct.unpack_from('<f',mesh(document.catalog,family+'?lod=0&mesh').positions)[0]
after=struct.unpack_from('<f',mesh(check,family+'?lod=0&mesh').positions)[0]
assert abs(after-before-.01)<1e-5;document.close()
result={'scope':'one actual placed model; three native LODs/two materials each','blender':bpy.app.version_string,
    'lods':3,'triangles':counts,'deformation_readback':True,'seconds':time.perf_counter()-start,'warnings':warnings,'game_verified':False}
output.with_suffix('.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='warnings'}))
addon.unregister()
