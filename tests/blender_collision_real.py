"""Bounded actual collision preview/edit; no whole-track output or game execution."""
from pathlib import Path
import sys,json,time,hashlib
import bpy

args=sys.argv[sys.argv.index('--')+1:];repo=Path(args[0]).resolve();source=args[1];output=Path(args[2]).resolve()
sys.path.insert(0,str(repo/'addon'))
import alterego_track_editor as addon
addon.register()
from alterego_track_editor import jobs,native_ui,collision_ui
from alterego_track_editor.physics_terrain import PhysicsTerrain
RealDocument=native_ui.TrackDocument
class SampleDocument(RealDocument):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.records=[r.copy() for r in self.records if r['physics']][:1]
        assert self.records,'No native collision binding'
        self.records[0]['terrain']='' # Keep this test focused on collision, not visual terrain preview.
        self.by_id={r['id']:r for r in self.records}
native_ui.TrackDocument=SampleDocument
start=time.perf_counter();root,_=jobs.drain(native_ui.import_steps(bpy.context,source))
obj=next(o for o in root.all_objects if o.get('ate_native_id'));bpy.context.view_layer.objects.active=obj
assert bpy.ops.alterego_track.load_collision(radius=0,max_cells=2)=={'FINISHED'}
obj=bpy.context.active_object;group=collision_ui.collision_group(root,obj)
doc=RealDocument(source);raw=doc.catalog.read(group['ate_collision_uri']);parsed=PhysicsTerrain(raw)
assert collision_ui.surface_changes(bpy.context,group,parsed)=={}
bpy.context.scene.ate_collision_code='RMBL';assert bpy.ops.alterego_track.assign_collision_code()=={'FINISHED'}
changes=collision_ui.surface_changes(bpy.context,group,parsed);edited=parsed.edit_codes(changes)
assert PhysicsTerrain(edited).version==0x20004
output.parent.mkdir(parents=True,exist_ok=True);output.with_suffix('.jpak').write_bytes(edited)
result={'blender':bpy.app.version_string,'source_cells':len(parsed.cells),'preview_cells':len(group.objects),
    'preview_triangles':sum(len(o.data.polygons) for o in group.objects),'changed_cells':len(changes),
    'source_hash_unchanged':hashlib.sha256(doc.catalog.read(group['ate_collision_uri'])).hexdigest()==hashlib.sha256(raw).hexdigest(),
    'seconds':time.perf_counter()-start,'game_verified':False}
output.with_suffix('.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
doc.close();addon.unregister()
