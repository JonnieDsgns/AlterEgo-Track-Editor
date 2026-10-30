"""Bounded real check: edited native LOD family placed as a new object; changes-only addons only (private outputs)."""
from pathlib import Path
import sys,json,time,zipfile
import bpy

args=sys.argv[sys.argv.index('--')+1:]
repo=Path(args[0]).resolve();source=args[1];output=Path(args[2]).resolve();output.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(repo/'addon'))
import alterego_track_editor as addon
addon.register()
from alterego_track_editor import native_ui,jobs,static_geometry_ui
from alterego_track_editor.native.storage import Catalog
from alterego_track_editor.native.geometry import mesh
from alterego_track_editor.native.formats.pkg_tree import Tree,patch_edits
RealDocument=native_ui.TrackDocument
family='eaid://environment_package/core_assets/objects/idf/barriers/armco_monaco_white_b.idf'
class SampleDocument(RealDocument):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.records=[r for r in self.records if r['model']==family+'?context=render' and not r['render_error'] and not r['clone_reason']][:1]
        assert len(self.records)==1,'Target template has no supported placed instance'
        self.by_id={r['id']:r for r in self.records}
native_ui.TrackDocument=SampleDocument
start=time.perf_counter()
root,warnings=jobs.drain(native_ui.import_steps(bpy.context,source))
native=next(o for o in root.all_objects if o.get('ate_native_id'))
bpy.context.view_layer.objects.active=native;native.select_set(True)
assert bpy.ops.alterego_track.load_geometry_lods()=={'FINISHED'}
group=static_geometry_ui.geometry_group(root,bpy.context.active_object)
for obj in group.objects:
    obj.data.vertices[0].co.z+=0.5;obj.data.update()
bpy.context.scene.cursor.location=native.matrix_world.translation
bpy.context.scene.cursor.location.x+=6
assert bpy.ops.alterego_track.place_edited_asset(asset_name='white_b_raised')=={'FINISHED'}
results={}
for fmt in ('PKG','REPLACE'):
    target=output/f'asset-{fmt.lower()}.swoftyaddon'
    assert bpy.ops.alterego_track.export_native_update(filepath=str(target),mode='PATCH',edit_format=fmt)=={'FINISHED'}
    with zipfile.ZipFile(target) as z:
        ops=json.loads(z.read('operations/erp.json'))['ops'];shipped=output/f'asset-{fmt.lower()}.erp';shipped.write_bytes(z.read('assets/new-assets.erp'))
        layer_op=ops[-1]
        if fmt=='REPLACE':replaced=z.read(layer_op['source'])
        else:edits=layer_op['edits']
    results[fmt]={'ops':len(ops),'copy_resources':sum(o['op']=='copy-resource' for o in ops)}
report=json.loads(bpy.data.texts[root['ate_export_report']].as_string());asset=report['new_assets']['white_b_raised']
check=Catalog();check.mount(output/'asset-pkg.erp')
triangles=[mesh(check,asset['family']+f'?lod={lod}&mesh').triangles for lod in range(3)]
doc=RealDocument(source)
try:
    replay=patch_edits(Tree(doc.layers[layer_op['resource']]['doc'].data),edits).to_bytes()
    assert replay==replaced,'Composable and whole-layer exports disagree'
finally:doc.close()
addon.unregister()
result={'scope':'one real armco_monaco_white_b placement, 3 LODs edited and placed as a new asset; changes-only addons, no full track copy',
 'blender':bpy.app.version_string,'family':asset['family'],'resources':asset['resources'],'formats':results,'lod_triangles':triangles,
 'composable_equals_whole_layer':True,'warnings':len(warnings),'seconds':round(time.perf_counter()-start,2),'game_verified':False}
(output/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
