"""Bounded real-source Blender insertion check; selected records only, private outputs, no full track copy."""
from pathlib import Path
import sys,json,time,zipfile
import bpy
from mathutils import Matrix
repo=Path(sys.argv[sys.argv.index('--')+1]).resolve();source=sys.argv[sys.argv.index('--')+2]
output=Path(sys.argv[sys.argv.index('--')+3]).resolve();output.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(repo/'addon'))
import alterego_track_editor as addon
addon.register()
from alterego_track_editor import native_ui,jobs
from alterego_track_editor.native.formats.pkg_tree import Tree,patch_edits
RealDocument=native_ui.TrackDocument
class SampleDocument(RealDocument):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        props=[r for r in self.records if not r['clone_reason'] and not r['render_error']]
        self.records=props[:24];self.by_id={r['id']:r for r in self.records}
native_ui.TrackDocument=SampleDocument
start=time.perf_counter();root,warnings=jobs.drain(native_ui.import_steps(bpy.context,source))
prop=next(o for o in root.all_objects if o.type=='MESH' and o.get('ate_native_cloneable'))
for o in bpy.context.selected_objects:o.select_set(False)
prop.select_set(True);bpy.context.view_layer.objects.active=prop
assert bpy.ops.alterego_track.duplicate_native_placement()=={'FINISHED'}
source_name=prop.name;clone=bpy.context.active_object;clone.matrix_world=Matrix.Translation((0,4,0))@clone.matrix_world
bpy.ops.wm.save_as_mainfile(filepath=str(output/'real-insertion.blend'))
bpy.ops.wm.open_mainfile(filepath=str(output/'real-insertion.blend'))
results={}
for fmt in ('PKG','REPLACE'):
    target=output/f'update-{fmt.lower()}.swoftyaddon'
    assert bpy.ops.alterego_track.export_native_update(filepath=str(target),mode='PATCH',edit_format=fmt)=={'FINISHED'}
    with zipfile.ZipFile(target) as z:
        ops=json.loads(z.read('operations/erp.json'))['ops'];provenance=json.loads(z.read('provenance.json'))
        results[fmt]={'ops':len(ops),'kinds':sorted({o['op'] for o in ops}),'inserted':len(provenance['inserted_placements'])}
        if fmt=='REPLACE':replaced=z.read(ops[0]['source'])
        else:edits=ops[0]['edits'];uri=ops[0]['resource']
doc=RealDocument(source)
try:
    replay=patch_edits(Tree(doc.layers[uri]['doc'].data),edits).to_bytes()
    assert replay==replaced,'Composable and whole-layer exports disagree'
finally:doc.close()
addon.unregister()
result={'scope':'24 real static-prop records, one explicit duplicate, changes-only exports; no full track copy',
 'blender':bpy.app.version_string,'source_name':source_name,'formats':results,'composable_equals_whole_layer':True,
 'warnings':len(warnings),'seconds':round(time.perf_counter()-start,2),'game_verified':False}
(output/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
