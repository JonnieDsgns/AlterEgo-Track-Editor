"""Synthetic Blender native-edit round trip, including source/render transform separation."""
from pathlib import Path
import sys,json
import bpy
from mathutils import Matrix
repo=Path(sys.argv[sys.argv.index('--')+1]).resolve()
out=Path(sys.argv[sys.argv.index('--')+2]).resolve();out.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(repo/'addon'));sys.path.insert(0,str(repo/'tests'))
from native_fixtures import make_track
import alterego_track_editor as addon
addon.register()
from alterego_track_editor import native_ui,jobs,marker_ui
from alterego_track_editor.native_project import TrackDocument
folder=out/'synthetic';make_track(folder)
real=TrackDocument
class TestDocument(real):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        for r in self.records:
            # Exercise nonidentity render-local transform separately from placement.
            render=Matrix.Translation((2,3,4))@Matrix.Diagonal((2,3,4,1))
            r['render']=native_ui.native_values(render)
native_ui.TrackDocument=TestDocument
root,warnings=jobs.drain(native_ui.import_steps(bpy.context,str(folder)))
assert not warnings
obj=next(o for o in root.all_objects if o.get('ate_native_id'))
assert abs(obj.matrix_world.translation.x-12)<1e-5
original=obj.matrix_world.copy();obj.matrix_world=Matrix.Translation((5,0,0))@original
bpy.context.view_layer.update()
doc=TestDocument(folder)
changes=native_ui.collect_changes(root,doc)
assert len(changes)==1
pose=next(iter(changes.values()));assert abs(pose[12]-15)<1e-5
assert max(abs(a-b) for a,b in zip(doc.records[0]['world'],pose) if a!=10)<1e-5
replacements=doc.apply(changes)
doc.write_updated(out/'updated',replacements)
check=real(out/'updated');assert abs(check.records[0]['world'][12]-15)<1e-5
# Source identity and editable state survive .blend persistence.
bpy.ops.wm.save_as_mainfile(filepath=str(out/'native.blend'))
bpy.ops.wm.open_mainfile(filepath=str(out/'native.blend'))
root=marker_ui.project(bpy.context)
assert root['ate_native_source']==str(folder)
# Removing an instance cannot silently disappear from export.
obj=next(o for o in root.all_objects if o.get('ate_native_id'))
bpy.data.objects.remove(obj,do_unlink=True)
try:native_ui.collect_changes(root,TestDocument(folder));raise AssertionError('Deletion silently accepted')
except ValueError as exc:assert 'Deleted' in str(exc)
addon.unregister()
result={'blender':bpy.app.version_string,'render_local_inverse':True,'native_matrix_readback':True,'save_reopen':True,'deletion_rejected':True,'game_verified':False}
(out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
