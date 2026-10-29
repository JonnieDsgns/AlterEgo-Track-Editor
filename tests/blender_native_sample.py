"""Small real-data regression, selected records only; no proprietary fixtures shipped."""
from pathlib import Path
import sys,itertools,json,time
import bpy
repo=Path(sys.argv[sys.argv.index('--')+1]).resolve();source=sys.argv[sys.argv.index('--')+2]
output=Path(sys.argv[sys.argv.index('--')+3]).resolve()
sys.path.insert(0,str(repo/'addon'))
import alterego_track_editor as addon
addon.register()
from alterego_track_editor import native_ui,jobs
RealDocument=native_ui.TrackDocument
class SampleDocument(RealDocument):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        render=[r for r in self.records if r['model'] and not r['render_error']]
        terrain=[r for r in self.records if r['terrain']]
        self.records=render[:24]+terrain[:1]
        self.by_id={r['id']:r for r in self.records}
    def terrain_geometry(self,r):return itertools.islice(super().terrain_geometry(r),2)
native_ui.TrackDocument=SampleDocument
start=time.perf_counter();root,warnings=jobs.drain(native_ui.import_steps(bpy.context,source))
doc=SampleDocument(source)
assert native_ui.collect_changes(root,doc)=={}
output.parent.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(output.with_suffix('.blend')))
bpy.ops.wm.open_mainfile(filepath=str(output.with_suffix('.blend')))
root=next(c for c in bpy.data.collections if c.get('ate_native_source'))
assert native_ui.collect_changes(root,doc)=={}
mat=next((m.material for obj in root.all_objects if obj.type=='MESH' for m in obj.material_slots if m.material),None)
assert mat is not None
mesh=next(obj for obj in root.all_objects if obj.type=='MESH' and obj.get('ate_native_id'))
mesh.location.x+=1
changes=native_ui.collect_changes(root,doc);assert len(changes)==1
replacements=doc.apply(changes);assert len(replacements)==1
# This verifies serialized layer values, without copying/installing a whole track.
from alterego_track_editor.native.formats.pkg import Document
for uri,payload in replacements.items():Document(payload)
output.parent.mkdir(parents=True,exist_ok=True)
result={'scope':'24 placed records plus at most two terrain draws; real source, headless',
 'blender':bpy.app.version_string,'objects':len(root.all_objects),'materials':len(bpy.data.materials),
 'images':len(bpy.data.images),'warnings':warnings,'seconds':time.perf_counter()-start,
 'noop_changes':0,'moved_layer_readback':True,'game_verified':False}
output.write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='warnings'}))
doc.close();addon.unregister()
