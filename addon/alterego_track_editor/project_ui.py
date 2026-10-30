"""Project identity and companion storage integrated with stable Workshop collections."""
import json
from pathlib import Path
import uuid
import bpy
from bpy.props import StringProperty
from . import marker_ui, collection_layout, project_store, ui_cache


def initialize(root):
    if not root.get('tw_project_id'):
        root['tw_project_id'] = str(uuid.uuid4())
    root['ate_schema'] = project_store.SCHEMA
    root['ate_required_variants'] = 'f1,f1_myteam,f2,f1_26,f1_26_myteam,f2_26,classic'
    if not root.get('ate_track_code'):
        root['ate_track_code'] = 'new_track'
    if not root.get('ate_sources'):
        root['ate_sources'] = '[]'
    if not root.get('ate_companion'):
        root['ate_companion'] = ''
    return root


def initialize_import(root):
    initialize(root)
    folder = Path(root['tw_track_folder'])
    paths = {Path(obj['tw_source_model']) for obj in root.all_objects if obj.get('tw_source_model')}
    paths.add(folder / root['tw_layout_manifest'])
    paths.update(p for p in (folder/'data.acd', folder/'data/surfaces.ini') if p.is_file())
    root['ate_sources'] = json.dumps([project_store.fingerprint(p) for p in sorted(paths) if p.is_file()])


def current(context):
    return marker_ui.project(context)


class ATE_OT_new_project(bpy.types.Operator):
    bl_idname = 'alterego_track.new_project'
    bl_label = 'New Track Project'
    bl_options = {'REGISTER', 'UNDO'}
    name: StringProperty(name='Project name', default='New Track')
    code: StringProperty(name='Track code', default='new_track')

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        try:
            project_store.validate_code(self.code)
        except ValueError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        root = bpy.data.collections.new(self.name)
        context.scene.collection.children.link(root)
        initialize(root)
        root['ate_track_code'] = self.code
        collection_layout.ensure(root)
        context.scene.tw_marker_project = root
        context.scene.tw_project_pinned = True
        ui_cache.invalidate('project')
        return {'FINISHED'}


class ATE_OT_companion(bpy.types.Operator):
    bl_idname = 'alterego_track.create_companion'
    bl_label = 'Save Companion Manifest'
    directory: StringProperty(name='Companion folder', subtype='DIR_PATH')

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        root = current(context)
        if root is None:
            return {'CANCELLED'}
        initialize(root)
        try:
            if not self.directory.strip():
                raise ValueError('Choose a companion folder')
            path = project_store.create_manifest(bpy.path.abspath(self.directory), root['tw_project_id'],
                                                 root['ate_track_code'], json.loads(root['ate_sources']))
            root['ate_companion'] = bpy.path.relpath(str(path.parent)) if bpy.data.filepath else str(path.parent)
        except (OSError, ValueError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, 'Companion project manifest created')
        return {'FINISHED'}


class ATE_OT_add_source(bpy.types.Operator):
    bl_idname = 'alterego_track.add_source'
    bl_label = 'Record Source File'
    bl_options = {'REGISTER', 'UNDO'}
    filepath: StringProperty(subtype='FILE_PATH')

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        root = current(context)
        if root is None:
            return {'CANCELLED'}
        try:
            record = project_store.fingerprint(bpy.path.abspath(self.filepath))
            initialize(root)
            rows = json.loads(root['ate_sources'])
            rows = [r for r in rows if r['path'] != record['path']] + [record]
            root['ate_sources'] = json.dumps(rows)
            root['ate_source_findings'] = '[]'
        except (OSError, ValueError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class ATE_OT_check_sources(bpy.types.Operator):
    bl_idname = 'alterego_track.check_sources'
    bl_label = 'Check Source Files'

    def execute(self, context):
        root = current(context)
        if root is None:
            return {'CANCELLED'}
        initialize(root)
        findings = project_store.check_sources(json.loads(root['ate_sources']))
        root['ate_source_findings'] = json.dumps(findings)
        self.report({'WARNING'} if findings else {'INFO'},
                    f'{len(findings)} missing or changed source files' if findings else 'Recorded sources match')
        return {'FINISHED'}


class ATE_OT_save_project(bpy.types.Operator):
    bl_idname = 'alterego_track.save_project'
    bl_label = 'Save Project'
    bl_description = 'Save your editable Blender project; no companion manifest is required'

    def execute(self, context):
        if bpy.data.filepath:
            return bpy.ops.wm.save_mainfile('INVOKE_DEFAULT')
        return bpy.ops.wm.save_as_mainfile('INVOKE_DEFAULT')


class ATE_PT_project(bpy.types.Panel):
    bl_label = 'Project Settings'
    bl_idname = 'ATE_PT_project'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'AlterEgo Track Editor'

    @classmethod
    def poll(cls, context):
        return context.scene.tw_workflow_stage == 'PROJECT'

    def draw(self, context):
        layout = self.layout
        root = marker_ui.ui_project(context)
        if root is None:
            layout.operator('alterego_track.new_project', icon='ADD')
            layout.label(text='Or import an Assetto Corsa track above')
            return
        layout.prop(root, 'name', text='Project name')
        layout.operator('alterego_track.save_project', icon='FILE_BLEND')
        layout.label(text='Your work is saved in the Blender file.')
        for row in json.loads(root.get('ate_source_findings', '[]')):
            status = 'has changed' if row['status'] == 'CHANGED' else 'is missing or unreadable'
            layout.label(text=Path(row['path']).name + ' ' + status, icon='ERROR')
        if root.get('ate_native_source'):
            layout.prop(context.scene,'ate_native_view')
            stats=json.loads(root.get('ate_native_stats','{}'))
            layout.label(text=f"{stats.get('mesh_objects',0)} mesh previews; {stats.get('warnings',0)} warnings")
            layout.operator('alterego_track.duplicate_native_placement', icon='DUPLICATE')
            layout.operator('alterego_track.export_native_update', icon='EXPORT')
            layout.label(text='Geometry LOD tools: Advanced Files', icon='INFO')
        else:
            layout.label(text='Native track export is still in development', icon='INFO')


class ATE_PT_project_advanced(bpy.types.Panel):
    bl_label = 'Advanced Files'
    bl_idname = 'ATE_PT_project_advanced'
    bl_parent_id = 'ATE_PT_project'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'AlterEgo Track Editor'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        root = marker_ui.ui_project(context)
        if root is None or not root.get('ate_schema'):
            return
        layout = self.layout
        layout.label(text='Optional source and companion-file tools')
        layout.prop(root, '["ate_track_code"]', text='Track identifier')
        layout.prop(root, '["ate_companion"]', text='Companion folder')
        layout.operator('alterego_track.create_companion', icon='FILE_FOLDER')
        layout.operator('alterego_track.add_source', icon='FILE')
        layout.operator('alterego_track.check_sources', icon='CHECKMARK')
        if root.get('ate_native_source'):
            layout.separator()
            layout.operator('alterego_track.load_geometry_lods',icon='IMPORT')
            from .static_geometry_ui import geometry_group
            group=geometry_group(root,context.active_object)
            if group:
                row=None
                for i,item in enumerate(sorted(group.objects,key=lambda o:o.ate_geometry_lod)):
                    if i%4==0:row=layout.row(align=True)
                    row.operator('alterego_track.preview_geometry_lod',text=f'LOD {item.ate_geometry_lod}',depress=item==context.active_object).level=item.ate_geometry_lod
            if context.active_object and (context.active_object.get('ate_native_id') or context.active_object.get('ate_geometry_source_id')):
                layout.prop(context.active_object,'ate_geometry_lod')
            layout.operator('alterego_track.export_static_geometry_test',icon='MESH_DATA')
            layout.operator('alterego_track.export_static_geometry_test',text='Export Independent Asset',icon='EXPORT').independent=True
            layout.label(text='Geometry family only; no collision or track package')


CLASSES = (ATE_OT_new_project, ATE_OT_companion, ATE_OT_add_source, ATE_OT_check_sources,
           ATE_OT_save_project, ATE_PT_project, ATE_PT_project_advanced)

def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
