"""Standalone Track Workshop: AC tracks, surfaces, markers and lines."""
bl_info = {
    "name": "AlterEgo Track Editor",
    "author": "Yannick",
    "version": (0, 2, 4),
    "blender": (4, 5, 0),
    "location": "View3D > Sidebar > AlterEgo Track Editor",
    "description": "Import AC tracks and prepare surfaces, timing, lines, rules and material sources",
    "category": "Import-Export",
}

import bpy
from bpy.props import EnumProperty, StringProperty
from .source import layouts, models
from . import surface_ui, marker_ui, collection_ui, workspace, routes, rules, timing, materials, ui_cache, workflow, jobs, diagnostics
from . import export_ui, export_build, project_ui, native_ui, material_library, facility_library, static_geometry_ui

_items = {}


def layout_items(self, context):
    # Retain strings for Blender's dynamic enum lifetime.
    return _items.get(self.directory, [])


def layout_changed(self, context):
    try:
        self.model_summary = f"{len(models(self.directory, self.selected_layout))} model files"
    except (OSError, ValueError) as error:
        self.model_summary = str(error)


class TW_OT_choose_layout(bpy.types.Operator):
    bl_idname = "track_workshop.choose_layout"
    bl_label = "Import Track Layout"
    # The dialog hands off to a distinct undoable worker operator.

    directory: StringProperty(subtype="DIR_PATH", options={"HIDDEN"})
    selected_layout: EnumProperty(name="Layout", items=layout_items, update=layout_changed)
    model_summary: StringProperty(options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and not jobs.busy(context)

    def invoke(self, context, event):
        try:
            _items[self.directory] = [(row["id"], row["name"] + " (" + row["layout"] + ")", row["id"])
                                      for row in layouts(self.directory)]
            self.selected_layout = _items[self.directory][0][0]
        except (OSError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return context.window_manager.invoke_props_dialog(self, width=460)

    def draw(self, context):
        self.layout.prop(self, "selected_layout")
        self.layout.label(text=self.model_summary, icon="MESH_DATA")

    def execute(self, context):
        result = bpy.ops.track_workshop.import_layout(
            'INVOKE_DEFAULT', directory=self.directory, selected_layout=self.selected_layout)
        return {'CANCELLED'} if result == {'CANCELLED'} else {'FINISHED'}


class TW_OT_import_layout(jobs.CooperativeJob, bpy.types.Operator):
    bl_idname = 'track_workshop.import_layout'
    bl_label = 'Import Track Layout'
    bl_options = {'REGISTER', 'UNDO'}
    directory: StringProperty(subtype='DIR_PATH', options={'HIDDEN'})
    selected_layout: StringProperty(options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and not jobs.busy(context)

    def invoke(self, context, event):
        return self.execute(context)

    def build(self, context):
        from .importer import load_steps
        return load_steps(context, self.directory, self.selected_layout)

    def execute(self, context):
        try:
            if not bpy.app.background:
                return self.start(context, self.build(context))
            self.completed(context, jobs.drain(self.build(context)))
        except Exception as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}

    def completed(self, context, result):
        root, warnings = result
        project_ui.initialize_import(root)
        context.scene.tw_marker_project = root
        context.scene.tw_project_pinned = True
        self.report({"WARNING"} if warnings else {"INFO"},
                    f"Imported {root.name}" + (f", {len(warnings)} warnings" if warnings else ""))


class TW_OT_track_folder(bpy.types.Operator):
    bl_idname = "track_workshop.track_folder"
    bl_label = "Import Assetto Corsa Track"

    directory: StringProperty(name="Track folder", subtype="DIR_PATH")
    filter_folder: bpy.props.BoolProperty(default=True, options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and not jobs.busy(context)

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        try:
            layouts(self.directory)
        except (OSError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        bpy.ops.track_workshop.choose_layout("INVOKE_DEFAULT", directory=self.directory)
        return {"FINISHED"}


class TW_PT_import(bpy.types.Panel):
    bl_label = "AlterEgo Track Editor"
    bl_idname = "TW_PT_import"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AlterEgo Track Editor"

    def draw(self, context):
        workflow.header(self.layout, context)
        if workflow.stage(context, "PROJECT"):
            body = self.layout.column()
            body.enabled = not context.scene.tw_job_running
            body.operator("track_workshop.track_folder", icon="FILE_FOLDER")
            body.operator("alterego_track.import_native", icon="IMPORT")
            body.operator("track_workshop.open_workspace", icon="WORKSPACE")
            body.prop(context.scene, "tw_expert")
            if context.scene.tw_expert:
                body.operator("track_workshop.environment_world", icon="WORLD")
                body.prop(context.scene, "tw_live_checks")


def import_menu(self, context):
    self.layout.operator("track_workshop.track_folder", text="Assetto Corsa Track Folder", icon="FILE_FOLDER")


CLASSES = (TW_OT_import_layout, TW_OT_choose_layout, TW_OT_track_folder, TW_PT_import)


def register():
    if bpy.app.version < (4, 5, 0):
        raise RuntimeError("AlterEgo Track Editor requires Blender 4.5 or later")
    if hasattr(bpy.types.Scene, "tw_asset_target"):
        raise RuntimeError("Disable Track Workshop before enabling AlterEgo Track Editor")
    ui_cache.register()
    jobs.register()
    workflow.register()
    surface_ui.register()
    marker_ui.register()
    collection_ui.register()
    routes.register()
    rules.register()
    timing.register()
    materials.register()
    diagnostics.register()
    export_ui.register()
    export_build.register()
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    workspace.register()
    project_ui.register()
    native_ui.register()
    material_library.register()
    facility_library.register()
    static_geometry_ui.register()
    bpy.types.TOPBAR_MT_file_import.append(import_menu)


def unregister():
    jobs.reset()
    static_geometry_ui.unregister()
    facility_library.unregister()
    material_library.unregister()
    native_ui.unregister()
    project_ui.unregister()
    workspace.unregister()
    ui_cache.unregister()
    export_build.unregister()
    export_ui.unregister()
    diagnostics.unregister()
    materials.unregister()
    timing.unregister()
    rules.unregister()
    routes.unregister()
    bpy.types.TOPBAR_MT_file_import.remove(import_menu)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    collection_ui.unregister()
    marker_ui.unregister()
    surface_ui.unregister()
    workflow.unregister()
    jobs.unregister()
    _items.clear()
