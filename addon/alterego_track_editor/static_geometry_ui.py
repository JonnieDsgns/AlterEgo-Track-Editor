"""Blender evaluated-mesh adapter for the isolated static geometry compiler."""
import json
import math
from pathlib import Path
import bpy
from bpy.props import StringProperty
from . import jobs,marker_ui,project_store
from .native_project import TrackDocument
from .native_ui import AXES
from .static_geometry import StaticInput,StaticTemplate,write_test


def evaluated_input(context,obj,template):
    if obj.type!='MESH' or obj.data.shape_keys or obj.animation_data:
        raise ValueError('Select an unanimated static mesh without shape keys')
    obj.update_from_editmode()
    obj.data.update()
    obj.update_tag(refresh={'DATA'})
    context.view_layer.update()
    evaluated=obj.evaluated_get(context.evaluated_depsgraph_get())
    data=evaluated.to_mesh(preserve_all_data_layers=True,depsgraph=context.evaluated_depsgraph_get())
    try:
        data.calc_loop_triangles()
        if not data.loop_triangles:raise ValueError('The selected mesh has no triangles')
        if any(t.material_index!=0 for t in data.loop_triangles):
            raise ValueError('The current static template supports one material slot')
        keys=set(template.streams)-{(1,0)}
        required_uv=4 if (5,1) in keys else 2 if (5,0) in keys else 1 if (3,0) in keys else 0
        if len(data.uv_layers)<required_uv:
            raise ValueError(f'This template needs {required_uv} explicit UV layers (two per native UV stream)')
        if (3,0) in keys:data.calc_tangents(uvmap=data.uv_layers[0].name)
        colour=data.color_attributes.active_color
        if (6,0) in keys and (colour is None or colour.domain not in ('CORNER','POINT')):
            raise ValueError('This template needs an active vertex colour layer')
        axes=AXES.inverted().to_3x3()
        positions=[];indices=[];attributes={k:[] for k in keys};lookup={}
        for triangle in data.loop_triangles:
            for corner in triangle.loops:
                loop=data.loops[corner]
                p=tuple(axes@data.vertices[loop.vertex_index].co)
                values={}
                for key in keys:
                    if key==(2,0):values[key]=tuple((axes@data.corner_normals[corner].vector).normalized())
                    elif key==(3,0):values[key]=(*tuple((axes@loop.tangent).normalized()),loop.bitangent_sign)
                    elif key[0]==5:
                        layer=key[1]*2
                        values[key]=(*data.uv_layers[layer].data[corner].uv,*data.uv_layers[layer+1].data[corner].uv)
                    elif key==(6,0):
                        index=corner if colour.domain=='CORNER' else loop.vertex_index
                        rgba=colour.data[index].color
                        if any(not math.isfinite(v) or not 0<=v<=1 for v in rgba):
                            raise ValueError('Native byte vertex colours require values from zero to one')
                        values[key]=tuple(round(v*255) for v in rgba)
                identity=(p,tuple((k,values[k]) for k in sorted(keys)))
                if identity not in lookup:
                    lookup[identity]=len(positions);positions.append(p)
                    for key in keys:attributes[key].append(values[key])
                indices.append(lookup[identity])
        return StaticInput(positions,indices,attributes)
    finally:evaluated.to_mesh_clear()


class ATE_OT_static_geometry_test(bpy.types.Operator):
    bl_idname='alterego_track.export_static_geometry_test'
    bl_label='Export Selected Geometry Test'
    bl_description='Write evaluated local geometry into a separate native ERP test copy; no track placement, collision or material edits'
    filepath:StringProperty(subtype='FILE_PATH')
    filter_glob:StringProperty(default='*.erp',options={'HIDDEN'})

    @classmethod
    def poll(cls,context):
        root=marker_ui.ui_project(context);obj=context.active_object
        return root is not None and bool(root.get('ate_native_source')) and obj is not None and bool(obj.get('ate_native_id')) and obj.type=='MESH' and not jobs.busy(context)

    def invoke(self,context,event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self,context):
        root=marker_ui.project(context);obj=context.active_object;document=None
        try:
            if project_store.check_sources(json.loads(root['ate_sources'])):
                raise ValueError('Source files changed or are missing; reimport before exporting')
            document=TrackDocument(root['ate_native_source'],root.get('ate_native_base') or None)
            record=document.by_id.get(obj.get('ate_native_id'))
            if record is None or record['render_error'] or not record['model'].endswith('?context=render'):
                raise ValueError('Select an imported native static model with resolved render placement')
            if not any(o==obj for o in root.all_objects):raise ValueError('Selected mesh belongs to another project')
            from .native_materials import signature
            if [m.material.get('ate_native_material') if m.material else None for m in obj.material_slots]!=json.loads(obj.get('ate_imported_materials','[]')):
                raise ValueError('This geometry test retains original native material bindings')
            if any(m.material and signature(m.material)!=m.material.get('ate_preview_signature') for m in obj.material_slots):
                raise ValueError('Edited materials need the native material writer')
            uri=record['model'][:-len('?context=render')]+'?lod=0&mesh'
            template=StaticTemplate(document.catalog,uri)
            report=write_test(document.catalog,uri,evaluated_input(context,obj,template),bpy.path.abspath(self.filepath))
            root['ate_last_geometry_test']=json.dumps(report)
        except Exception as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        finally:
            if document:document.close()
        self.report({'INFO'},f"Geometry test: {report['triangles']} triangles; no collision or complete track package")
        return {'FINISHED'}


def register():bpy.utils.register_class(ATE_OT_static_geometry_test)
def unregister():bpy.utils.unregister_class(ATE_OT_static_geometry_test)
