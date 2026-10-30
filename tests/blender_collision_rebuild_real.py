"""Bounded real check: whole-track legacy collision rebuild with one edited native cell and one authored mesh; private output."""
from pathlib import Path
import sys,json,time,zipfile
import bpy
from mathutils import Vector
args=sys.argv[sys.argv.index('--')+1:]
repo=Path(args[0]).resolve();source=args[1];output=Path(args[2]).resolve();output.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(repo/'addon'))
import alterego_track_editor as addon
addon.register()
from alterego_track_editor import native_ui,jobs
from alterego_track_editor.physics_terrain import PhysicsTerrain,triangle_soup
RealDocument=native_ui.TrackDocument
class SampleDocument(RealDocument):
    def __init__(self,*a,**k):
        super().__init__(*a,**k)
        self.records=[r for r in self.records if r['physics']][:1]+[r for r in self.records if not r['clone_reason']][:3];self.by_id={r['id']:r for r in self.records}
    def terrain_geometry(self,r):return iter(())
native_ui.TrackDocument=SampleDocument
start=time.perf_counter();root,_=jobs.drain(native_ui.import_steps(bpy.context,source))
terrain=next(o for o in root.all_objects if o.name.endswith('PhysicsTerrain'))
bpy.context.view_layer.objects.active=terrain
assert bpy.ops.alterego_track.load_collision(radius=0,max_cells=1)=={'FINISHED'}
cell=bpy.context.active_object;cell.data.vertices[0].co+=Vector((0,0,0.25));cell.data.update()
code=cell.material_slots[cell.data.polygons[0].material_index].material['ate_physics_code']
mesh=bpy.data.meshes.new('Authored pad');mesh.from_pydata([(0,0,0),(4,0,0),(0,4,0)],[],[(0,1,2)])
pad=bpy.data.objects.new('Authored pad',mesh);root.objects.link(pad);pad.location=cell.matrix_world@cell.data.vertices[0].co+Vector((0,0,1))
pad.tw_surface.collision=True;pad.ate_physics_code=code
target=output/'collision.swoftyaddon'
assert bpy.ops.alterego_track.export_native_update(filepath=str(target),mode='PATCH',edit_format='PKG',rebuild_collision=True)=={'FINISHED'}
with zipfile.ZipFile(target) as z:ops=json.loads(z.read('operations/erp.json'))['ops'];legacy=PhysicsTerrain(z.read(ops[0]['source']),0x20002)
report=json.loads(bpy.data.texts[root['ate_export_report']].as_string())['collision_rebuild']
addon.unregister()
result={'scope':'real track: one native collision cell edited in Blender plus one authored triangle; whole-track legacy rebuild in a changes-only addon',
 'blender':bpy.app.version_string,'ops':[o['op'] for o in ops],'legacy_cells':len(legacy.cells),'triangles':sum(c.triangles for c in legacy.cells),
 'report':{k:report[k] for k in ('native_triangles','edited_cells','authored_triangles','triangles','cells','codes')},'authored_code':code,
 'seconds':round(time.perf_counter()-start,1),'game_verified':False}
(output/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
