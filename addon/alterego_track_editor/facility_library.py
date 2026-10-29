"""Actual model assemblies for reference placement; native insertion is a separate writer."""
import json
import bpy
from bpy.props import EnumProperty
from mathutils import Matrix,Vector
from . import marker_ui,collection_layout

_items=[]


def refresh():
    global _items
    _items=[]
    for index,c in enumerate(sorted((c for c in bpy.data.collections if c.get('ate_facility_template')),key=lambda c:c.name)):
        if not bpy.app.background:
            c.asset_mark();c.asset_generate_preview()
        _items.append((c.name,c.name,'Facility assembly',c.preview_ensure().icon_id,index+1))


def items(self,context):
    return _items or [('NONE','No facility templates','Select model parts and create a template',0,0)]


class ATE_OT_facility_template(bpy.types.Operator):
    bl_idname='alterego_track.create_facility_template'
    bl_label='Create Template from Selection'
    bl_description='Explicitly copy selected model parts and their children into a reusable library assembly'
    bl_options={'REGISTER','UNDO'}

    def execute(self,context):
        selected=set(context.selected_objects)
        for obj in list(selected):selected.update(obj.children_recursive)
        if not selected or context.active_object is None:
            self.report({'ERROR'},'Select the facility parts and an active placement anchor')
            return {'CANCELLED'}
        template=bpy.data.collections.new('Facility / '+context.active_object.name)
        template['ate_facility_template']=True;template.use_fake_user=True
        anchor=context.active_object.matrix_world.copy()
        copied={};worlds={}
        for source in selected:
            obj=source.copy()
            # Explicit template copy retains geometry/material sharing.
            if obj.get('ate_native_id'):
                obj['ate_template_native_origin']=obj['ate_native_id'];del obj['ate_native_id']
            obj['ate_reference_only']=True
            template.objects.link(obj);copied[source]=obj
            worlds[source]=anchor.inverted()@source.matrix_world
        for source,obj in copied.items():
            obj.parent=copied.get(source.parent)
            obj.matrix_world=worlds[source]
        context.view_layer.update()
        points=[worlds[source]@Vector(corner) for source in selected if source.type=='MESH' for corner in source.bound_box]
        if points:
            template['ate_bounds']=[min(p[k] for p in points) for k in range(3)]+[max(p[k] for p in points) for k in range(3)]
        refresh()
        return {'FINISHED'}


class ATE_OT_place_facility(bpy.types.Operator):
    bl_idname='alterego_track.place_facility'
    bl_label='Place at 3D Cursor'
    bl_options={'REGISTER','UNDO'}

    def execute(self,context):
        template=bpy.data.collections.get(context.scene.ate_facility_template)
        root=marker_ui.project(context)
        if template is None or not template.get('ate_facility_template') or root is None:
            self.report({'ERROR'},'Choose a facility template and a track project')
            return {'CANCELLED'}
        obj=bpy.data.objects.new(template.name,None)
        obj.instance_type='COLLECTION';obj.instance_collection=template
        obj['ate_facility_preview']=True;obj['ate_reference_only']=True
        obj['tw_project_id']=root['tw_project_id']
        collection_layout.ensure(root)['COMMON_FACILITIES'].objects.link(obj)
        obj.location=context.scene.cursor.location
        if template.get('ate_bounds'):
            low,high=list(template['ate_bounds'])[:3],list(template['ate_bounds'])[3:]
            points=[(x,y,z) for x in (low[0],high[0]) for y in (low[1],high[1]) for z in (low[2],high[2])]
            edges=[(i,j) for i in range(8) for j in range(i+1,8) if bin(i^j).count('1')==1]
            data=bpy.data.meshes.new('Facility Geometry Bounds');data.from_pydata(points,edges,[])
            bounds=bpy.data.objects.new('Geometry Bounds',data)
            collection_layout.ensure(root)['COMMON_FACILITIES'].objects.link(bounds)
            bounds.parent=obj;bounds.display_type='WIRE';bounds.hide_render=True
            bounds['ate_reference_only']=True;bounds['tw_project_id']=root['tw_project_id']
        bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);context.view_layer.objects.active=obj
        self.report({'INFO'},'Facility reference placed; native facility insertion is still in development')
        return {'FINISHED'}


class ATE_OT_facility_overlaps(bpy.types.Operator):
    bl_idname='alterego_track.check_facility_overlaps'
    bl_label='Check Facility Overlaps'

    def execute(self,context):
        root=marker_ui.project(context)
        if root is None:return {'CANCELLED'}
        rows=[]
        for obj in root.all_objects:
            if not obj.get('ate_facility_preview') or not obj.instance_collection.get('ate_bounds'):continue
            low,high=list(obj.instance_collection['ate_bounds'])[:3],list(obj.instance_collection['ate_bounds'])[3:]
            points=[obj.matrix_world@Vector((x,y,z)) for x in (low[0],high[0]) for y in (low[1],high[1]) for z in (low[2],high[2])]
            rows.append((obj,[min(p[k] for p in points) for k in range(3)],[max(p[k] for p in points) for k in range(3)]))
        overlaps=[]
        for i,(a,al,ah) in enumerate(rows):
            for b,bl,bh in rows[i+1:]:
                if all(min(ah[k],bh[k])-max(al[k],bl[k])>1e-4 for k in range(3)):
                    overlaps.append([a.name,b.name])
        root['ate_facility_overlaps']=json.dumps(overlaps)
        self.report({'WARNING'} if overlaps else {'INFO'},f'{len(overlaps)} possible facility overlaps (bounding boxes only)')
        return {'FINISHED'}


class ATE_PT_facilities(bpy.types.Panel):
    bl_idname='ATE_PT_facilities';bl_label='Facility Placement Previews'
    bl_space_type='VIEW_3D';bl_region_type='UI';bl_category='AlterEgo Track Editor'

    @classmethod
    def poll(cls,context):return context.scene.tw_workflow_stage=='GEOMETRY'

    def draw(self,context):
        layout=self.layout
        layout.operator('alterego_track.create_facility_template',icon='ADD')
        layout.template_icon_view(context.scene,'ate_facility_template',show_labels=True,scale=5)
        layout.operator('alterego_track.place_facility',icon='EMPTY_AXIS')
        layout.operator('alterego_track.check_facility_overlaps',icon='VIEWZOOM')
        layout.label(text='Actual model reference; bounds are not physical clearance')
        layout.label(text='Native insertion is still in development',icon='INFO')
        root=marker_ui.ui_project(context)
        if root:
            for a,b in json.loads(root.get('ate_facility_overlaps','[]')):
                layout.label(text=a+' / '+b,icon='ERROR')


CLASSES=(ATE_OT_facility_template,ATE_OT_place_facility,ATE_OT_facility_overlaps,ATE_PT_facilities)

def register():
    for cls in CLASSES:bpy.utils.register_class(cls)
    bpy.types.Scene.ate_facility_template=EnumProperty(name='Facility',items=items)
    refresh()

def unregister():
    global _items
    del bpy.types.Scene.ate_facility_template
    for cls in reversed(CLASSES):bpy.utils.unregister_class(cls)
    _items=[]
