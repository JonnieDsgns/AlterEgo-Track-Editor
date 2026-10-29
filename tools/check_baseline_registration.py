"""Background-only registration check of an explicitly supplied baseline snapshot."""
import importlib.util
import json
from pathlib import Path
import sys
import bpy
args=sys.argv[sys.argv.index('--')+1:]
source, destination=map(Path,args)
before=(set(bpy.data.workspaces),bpy.context.scene.world,set(bpy.app.handlers.load_post))
spec=importlib.util.spec_from_file_location('TrackWorkshop',source/'__init__.py',submodule_search_locations=[str(source)])
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
for cycle in range(2):
 m.register()
 assert hasattr(bpy.types.Scene,'tw_asset_target')
 m.unregister()
 assert not hasattr(bpy.types.Scene,'tw_asset_target')
assert set(bpy.data.workspaces)==before[0]
assert bpy.context.scene.world==before[1]
assert set(bpy.app.handlers.load_post)==before[2]
result={'blender':bpy.app.version_string,'cycles':2,'workspace_preserved':True,'world_preserved':True,'handlers_restored':True,'scope':'background registration only; no UI, assets, backend or game execution'}
destination.write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
