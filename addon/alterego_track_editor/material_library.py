"""Curated material assets with a Blender thumbnail grid and explicit application."""
import bpy
from bpy.props import EnumProperty,StringProperty

_all=[]
_visible=[]


def items(self,context):
    global _visible
    search=getattr(self,'ate_template_search','').lower()
    _visible=[row for row in _all if search in row[1].lower() or search in row[2].lower()]
    return _visible or [('NONE','No templates','Mark a material as a template or load a library',0,0)]


def refresh():
    global _all
    _all=[]
    for index,material in enumerate(sorted((m for m in bpy.data.materials if m.get('ate_library_template')),key=lambda m:m.name)):
        if not bpy.app.background:
            material.asset_mark()
            material.asset_generate_preview()
        preview=material.preview_ensure()
        _all.append((material.name,material.name,str(material.get('ate_native_shader','')),preview.icon_id,index+1))


class ATE_OT_mark_template(bpy.types.Operator):
    bl_idname='alterego_track.mark_material_template'
    bl_label='Add Material to Templates'
    bl_options={'REGISTER','UNDO'}

    @classmethod
    def poll(cls,context):
        return context.object is not None and context.object.active_material is not None

    def execute(self,context):
        source=context.object.active_material
        if not source.get('ate_library_template'):
            template=source.copy();template.name='Template / '+source.name
            template.use_fake_user=True;template['ate_library_template']=True
            template['ate_template_source']=source.get('ate_native_material','Blender authored')
        refresh()
        return {'FINISHED'}


class ATE_OT_refresh_templates(bpy.types.Operator):
    bl_idname='alterego_track.refresh_templates'
    bl_label='Refresh Template Previews'

    def execute(self,context):
        refresh();return {'FINISHED'}


class ATE_OT_apply_template(bpy.types.Operator):
    bl_idname='alterego_track.apply_template'
    bl_label='Apply Template'
    bl_options={'REGISTER','UNDO'}

    def execute(self,context):
        template=bpy.data.materials.get(context.scene.ate_material_template)
        if template is None or not template.get('ate_library_template'):
            self.report({'ERROR'},'Choose a material template first')
            return {'CANCELLED'}
        targets=[o for o in context.selected_objects if o.type=='MESH' and o.is_editable]
        if not targets:
            self.report({'ERROR'},'Select an editable mesh or faces')
            return {'CANCELLED'}
        material=template.copy();material.name=template.name.removeprefix('Template / ')+' (Instance)'
        material.use_fake_user=False;del material['ate_library_template']
        material['ate_template_instance']=True
        for obj in targets:
            if obj.mode=='EDIT':
                import bmesh
                bm=bmesh.from_edit_mesh(obj.data)
                faces=[face for face in bm.faces if face.select]
                if not faces:continue
                obj.data.materials.append(material);index=len(obj.data.materials)-1
                for face in faces:face.material_index=index
                bmesh.update_edit_mesh(obj.data)
            else:
                if not obj.material_slots:obj.data.materials.append(None)
                obj.material_slots[obj.active_material_index].link='OBJECT'
                obj.active_material=material
        return {'FINISHED'}


class ATE_OT_load_templates(bpy.types.Operator):
    bl_idname='alterego_track.load_templates'
    bl_label='Load Template Library'
    bl_options={'REGISTER','UNDO'}
    filepath:StringProperty(subtype='FILE_PATH')
    filter_glob:StringProperty(default='*.blend',options={'HIDDEN'})

    def invoke(self,context,event):
        context.window_manager.fileselect_add(self);return {'RUNNING_MODAL'}

    def execute(self,context):
        try:
            with bpy.data.libraries.load(bpy.path.abspath(self.filepath),link=False) as (source,target):
                target.materials=source.materials
            for material in target.materials:
                if material:
                    material['ate_library_template']=True;material.use_fake_user=True
            refresh()
        except Exception as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class ATE_PT_material_templates(bpy.types.Panel):
    bl_idname='ATE_PT_material_templates'
    bl_label='Material Templates'
    bl_space_type='VIEW_3D';bl_region_type='UI';bl_category='AlterEgo Track Editor'

    @classmethod
    def poll(cls,context):
        return context.scene.tw_workflow_stage=='MATERIALS'

    def draw(self,context):
        layout=self.layout
        layout.operator('alterego_track.load_templates',icon='FILE_FOLDER')
        layout.operator('alterego_track.mark_material_template',icon='ADD')
        layout.prop(context.scene,'ate_template_search',text='',icon='VIEWZOOM')
        layout.template_icon_view(context.scene,'ate_material_template',show_labels=True,scale=5)
        layout.operator('alterego_track.apply_template',icon='CHECKMARK')
        layout.operator('alterego_track.refresh_templates',icon='FILE_REFRESH')
        layout.label(text='Applies an editable copy; physical surfaces stay unchanged')
        layout.label(text='Native material export is still in development',icon='INFO')


CLASSES=(ATE_OT_mark_template,ATE_OT_refresh_templates,ATE_OT_apply_template,ATE_OT_load_templates,ATE_PT_material_templates)

def register():
    for cls in CLASSES:bpy.utils.register_class(cls)
    bpy.types.Scene.ate_material_template=EnumProperty(name='Template',items=items)
    bpy.types.Scene.ate_template_search=StringProperty(name='Search')
    refresh()

def unregister():
    global _all,_visible
    del bpy.types.Scene.ate_material_template;del bpy.types.Scene.ate_template_search
    for cls in reversed(CLASSES):bpy.utils.unregister_class(cls)
    _all=[];_visible=[]
