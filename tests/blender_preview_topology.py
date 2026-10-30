"""Preview meshes omit degenerate/duplicate native triangles and keep material groups aligned."""
from pathlib import Path
from types import SimpleNamespace
import sys,json,struct
import bpy
repo=Path(sys.argv[sys.argv.index('--')+1]).resolve();out=Path(sys.argv[sys.argv.index('--')+2]).resolve();out.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(repo/'addon'))
import alterego_track_editor as addon
addon.register()
from alterego_track_editor import native_ui
positions=[(0,0,0),(1,0,0),(0,0,1),(1,0,1),(2,0,0),(2,0,1)]
triangles=[(0,1,2),(1,1,3),(1,3,2),(2,1,3),(1,4,3),(4,5,3)]  # degenerate #1, duplicate #3 of #2
groups=[{'first':0,'count':9,'slot':'A'},{'first':9,'count':9,'slot':'B'}]
geometry=SimpleNamespace(positions=struct.pack(f'<{len(positions)*3}f',*[v for p in positions for v in p]),
    indices=struct.pack(f'<{len(triangles)*3}I',*[i for t in triangles for i in t]),uvs=[],normals=b'',groups=groups)
data=native_ui.create_mesh('fixture/terrain#0:0',geometry)
assert len(data.polygons)==4 and data['ate_preview_omitted_triangles']==2,(len(data.polygons),data['ate_preview_omitted_triangles'])
assert groups==[{'first':0,'count':6,'slot':'A'},{'first':6,'count':6,'slot':'B'}],groups
assert not data.validate(clean_customdata=False)
bad=SimpleNamespace(positions=geometry.positions,indices=struct.pack('<3I',0,0,1),uvs=[],normals=b'',groups=None)
try:native_ui.create_mesh('fixture/empty',bad);raise AssertionError('Empty preview accepted')
except ValueError as exc:assert 'no usable preview triangles' in str(exc)
addon.unregister()
result={'blender':bpy.app.version_string,'degenerate_and_duplicate_omitted':True,'groups_remapped':True,'empty_draw_rejected':True}
(out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
