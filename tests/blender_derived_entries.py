"""Synthetic Blender check: new placements get PVS/lightmap entries by default and none when the option is off."""
from pathlib import Path
import sys,json
import bpy
repo=Path(sys.argv[sys.argv.index('--')+1]).resolve();out=Path(sys.argv[sys.argv.index('--')+2]).resolve();out.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(repo/'addon'));sys.path.insert(0,str(repo/'tests'))
from native_fixtures import make_reference_track
import alterego_track_editor as addon
addon.register()
from alterego_track_editor import native_ui,jobs
from alterego_track_editor.native_project import TrackDocument
from alterego_track_editor.native.formats import pvs,lightmaps
source=make_reference_track(out/'track');original=source.read_bytes()
root,_=jobs.drain(native_ui.import_steps(bpy.context,str(out/'track')))
barrier=next(o for o in root.all_objects if o.name=='objects$barrier_a')
for o in bpy.context.selected_objects:o.select_set(False)
barrier.select_set(True);bpy.context.view_layer.objects.active=barrier
assert bpy.ops.alterego_track.duplicate_native_placement()=={'FINISHED'}
def read(path,suffix):
    doc=TrackDocument(path);uri=next(u for u in doc.catalog.by_uri if u.endswith(suffix));data=doc.catalog.read(uri);doc.close();return data
assert bpy.ops.alterego_track.export_native_update(filepath=str(out/'with'/'track'),mode='FULL')=={'FINISHED'}
names=[r[0] for r in pvs.read_objects(read(out/'with'/'track','.header.pvsbin'))]
assert len(names)==2 and names[1].startswith('objects$barrier_a_ate_'),names
assert len(lightmaps.read(read(out/'with'/'track','lightmap_locations')))==2
report=json.loads(bpy.data.texts[root['ate_export_report']].as_string())['new_placement_entries'];assert report['visibility'][0]['added']==1
assert bpy.ops.alterego_track.export_native_update(filepath=str(out/'without'/'track'),mode='FULL',derived_entries=False)=={'FINISHED'}
assert len(pvs.read_objects(read(out/'without'/'track','.header.pvsbin')))==1 and len(lightmaps.read(read(out/'without'/'track','lightmap_locations')))==1
assert source.read_bytes()==original
addon.unregister()
result={'blender':bpy.app.version_string,'default_adds_visibility_and_lighting':True,'option_off_leaves_them':True,'source_unchanged':True,'game_verified':False}
(out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
