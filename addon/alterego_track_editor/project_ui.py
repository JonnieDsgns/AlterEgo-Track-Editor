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


class ATE_PT_project(bpy.types.Panel):
    bl_label = 'Project Storage'
    bl_idname = 'ATE_PT_project'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'AlterEgo Track Editor'

    def draw(self, context):
        if context.scene.tw_workflow_stage != 'PROJECT':
            return
        layout = self.layout
        layout.operator('alterego_track.new_project', icon='ADD')
        root = marker_ui.ui_project(context)
        if root is None:
            return
        if not root.get('ate_schema'):
            layout.label(text='Import or create an AlterEgo project', icon='INFO')
            return
        layout.prop(root, '["ate_track_code"]', text='Track code')
        layout.prop(root, '["ate_companion"]', text='Companion folder')
        layout.operator('alterego_track.create_companion', icon='FILE_FOLDER')
        layout.operator('alterego_track.add_source', icon='FILE')
        layout.operator('alterego_track.check_sources', icon='CHECKMARK')
        for row in json.loads(root.get('ate_source_findings', '[]')):
            layout.label(text=Path(row['path']).name + ': ' + row['status'], icon='ERROR')
        layout.label(text='Save the editable project as a .blend')
        layout.label(text='Development foundation: native export not included', icon='INFO')


CLASSES = (ATE_OT_new_project, ATE_OT_companion, ATE_OT_add_source, ATE_OT_check_sources, ATE_PT_project)

def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
