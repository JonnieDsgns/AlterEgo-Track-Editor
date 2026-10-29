from pathlib import Path
import sys,time,json
import bpy
repo=Path(sys.argv[sys.argv.index('--')+1]).resolve();source=sys.argv[sys.argv.index('--')+2];output=Path(sys.argv[sys.argv.index('--')+3]).resolve()
sys.path.insert(0,str(repo/'addon'))
import alterego_track_editor as addon
addon.register()
from alterego_track_editor import native_ui
start=time.perf_counter();iterator=native_ui.import_steps(bpy.context,source)
last=-1
while True:
 try:
  progress,label=next(iterator)
  if int(progress*10)!=last:last=int(progress*10);print(label,flush=True)
 except StopIteration as done:
  root,warnings=done.value;break
result={'project':root['ate_track_code'],'objects':len(root.all_objects),'meshes':len(bpy.data.meshes),'materials':len(bpy.data.materials),'images':len(bpy.data.images),'warnings':len(warnings),'seconds':time.perf_counter()-start,'variants':json.loads(root['ate_native_variants']),'game_verified':False}
output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
addon.unregister()
