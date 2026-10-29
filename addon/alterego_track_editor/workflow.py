"""Task navigation and explicit, reversible view-layer-only working views."""
import textwrap

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, PointerProperty, StringProperty

from . import marker_ui, workspace

STAGES = (("PROJECT", "Project", "Project and import", "FILE_FOLDER", 0),
          ("GEOMETRY", "Geometry", "Assets and physical surfaces", "MESH_DATA", 1),
          ("TRACK", "Track", "Markers, lines, limits and timing", "TRACKING", 2),
          ("MATERIALS", "Materials", "Visual materials", "MATERIAL", 3),
          ("CHECKS", "Checks", "Central project review", "CHECKMARK", 4),
          ("EXPORT", "Export", "DatabaseEditor export", "EXPORT", 5))
TRACK_TABS = (("MARKERS", "Markers", "Starting grid and pit positions"),
              ("LINES", "Lines", "Racing line and widths"),
              ("RULES", "Limits and Pit Rules", "Legal boundaries and pit rules"),
              ("TIMING", "Timing", "Start / Finish and sectors"))
_project_items = []
_project_strings = {}


def stage(context, name, tab=None):
    return (getattr(context.scene, "tw_workflow_stage", "PROJECT") == name
            and (tab is None or context.scene.tw_track_tab == tab))


def own_active(context):
    root = marker_ui.ui_project(context)
    owner = marker_ui.ui_object_root(context, context.active_object)
    return owner is None or owner == root


class TW_PG_view_flag(bpy.types.PropertyGroup):
    role: StringProperty()
    hidden: BoolProperty()


class TW_PG_view_state(bpy.types.PropertyGroup):
    project: PointerProperty(type=bpy.types.Collection)
    layer: StringProperty()
    mode: StringProperty()
    flags: CollectionProperty(type=TW_PG_view_flag)


def view_record(context, root):
    return next((item for item in context.scene.tw_view_states
                 if item.project == root and item.layer == context.view_layer.name), None)


def view_targets(context, root):
    roots = []

    def locate(layer):
        if layer.collection == root:
            roots.append(layer)
        for child in layer.children:
            locate(child)
    locate(context.view_layer.layer_collection)
    if len(roots) != 1:
        raise ValueError("The project must appear exactly once in this View Layer.")
    result = {}

    def visit(layer):
        collection = layer.collection
        role = collection.get("tw_collection_role", "")
        if (collection.get("tw_collection_owner") == root["tw_project_id"]
                and (role in ("SOURCE", "COMMON") or role.startswith("YEAR_"))):
            if role in result:
                raise ValueError("Duplicate project collection role: " + role)
            result[role] = layer
        for child in layer.children:
            visit(child)
    visit(roots[0])
    if not {"SOURCE", "COMMON"}.issubset(result):
        raise ValueError("Use Prepare Collections before changing working views.")
    return result


def apply_view(context, root, mode):
    targets = view_targets(context, root)
    record = view_record(context, root)
    if mode == "RESTORE":
        if record is not None:
            for flag in record.flags:
                if flag.role in targets:
                    targets[flag.role].hide_viewport = flag.hidden
            index = next(i for i, item in enumerate(context.scene.tw_view_states) if item == record)
            context.scene.tw_view_states.remove(index)
        return
    if record is None:
        record = context.scene.tw_view_states.add()
        record.project, record.layer = root, context.view_layer.name
    baseline = {flag.role: flag.hidden for flag in record.flags}
    for role, layer in targets.items():
        if role not in baseline:
            flag = record.flags.add()
            flag.role, flag.hidden = role, layer.hide_viewport
            baseline[role] = flag.hidden
    for role, layer in targets.items():
        layer.hide_viewport = (mode == "EXPORT" if role == "SOURCE"
                               else True if mode == "SOURCE" else baseline[role])
    record.mode = mode


def project_items(self, context):
    global _project_items
    if context is None:
        return _project_items
    def keep(value):
        return _project_strings.setdefault(value, value)
    _project_items = [(keep(root["tw_project_id"]), keep(root.name), keep(root.name)) for root in marker_ui.ui_roots(context)]
    return _project_items


class TW_OT_choose_project(bpy.types.Operator):
    bl_idname = "track_workshop.choose_project"
    bl_label = "Choose Track Project"
    project_id: EnumProperty(name="Track", items=project_items)

    @classmethod
    def poll(cls, context):
        return bool(marker_ui.ui_roots(context))

    def invoke(self, context, event):
        project_items(self, context)
        root = marker_ui.project(context)
        if root is not None:
            self.project_id = root["tw_project_id"]
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        root = next((item for item in marker_ui.roots(context) if item["tw_project_id"] == self.project_id), None)
        if root is None:
            return {"CANCELLED"}
        context.scene.tw_marker_project = root
        context.scene.tw_project_pinned = True
        return {"FINISHED"}


class TW_OT_work_view(bpy.types.Operator):
    bl_idname = "track_workshop.work_view"
    bl_label = "Working View"
    bl_options = {"REGISTER", "UNDO"}
    mode: EnumProperty(items=(("SOURCE", "AC Source", "Show AC geometry and retain markup visibility"),
                              ("EXPORT", "F1 Preparation", "Hide AC source geometry in this View Layer"),
                              ("COMPARE", "Compare", "Show source and prepared geometry together"),
                              ("RESTORE", "Restore Visibility", "Restore visibility saved before the first view change")))

    @classmethod
    def description(cls, context, properties):
        return {"SOURCE": "AC Source", "EXPORT": "F1 Preparation", "COMPARE": "Compare",
                "RESTORE": "Restore previous visibility in this View Layer"}.get(properties.mode, "Working View")

    @classmethod
    def poll(cls, context):
        return marker_ui.ui_project(context) is not None and not context.scene.tw_job_running

    def execute(self, context):
        try:
            apply_view(context, marker_ui.project(context), self.mode)
        except ValueError as error:
            self.report({"WARNING"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


def apply_quality(context, mode):
    area = context.area
    if area is None or area.type != "VIEW_3D":
        area = next((item for item in context.screen.areas if item.type == "VIEW_3D"), None)
    if area is None:
        raise ValueError("Open a 3D View to change its preview mode.")
    space = area.spaces.active
    if mode == "WORK":
        space.shading.type = "SOLID"
    else:
        light = workspace.environment(context)
        space.shading.type = "MATERIAL"
        space.shading.use_scene_world = False
        space.shading.use_scene_lights = False
        space.shading.studio_light = light.name
        space.shading.studiolight_intensity = 1
        space.shading.studiolight_background_alpha = 1
        space.shading.studiolight_background_blur = 0


class TW_OT_preview_quality(bpy.types.Operator):
    bl_idname = "track_workshop.preview_quality"
    bl_label = "Viewport Mode"
    bl_description = "Change only this viewport; Work uses Solid, Materials loads the configured HDRI"
    mode: EnumProperty(items=(("WORK", "Work", "Fast Solid viewport"), ("MATERIAL", "Materials", "HDRI material preview")))

    def execute(self, context):
        try:
            apply_quality(context, self.mode)
        except (OSError, RuntimeError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


def header(layout, context):
    scene, root = context.scene, marker_ui.ui_project(context)
    if scene.tw_live_checks:
        layout.prop(scene, "tw_live_checks", icon="TIME")
    if root is not None:
        for line in textwrap.wrap(root.name, width=30):
            layout.label(text=line, icon="OUTLINER_COLLECTION")
        manifest = root.get("tw_layout_manifest", "")
        label = root.get("tw_layout_name") or ("Default" if manifest in ("models.ini", "@default_kn5") else manifest.removeprefix("models_").removesuffix(".ini").replace("_", " "))
        for line in textwrap.wrap("Layout: " + label, width=30):
            layout.label(text=line)
        from . import diagnostics, ui_cache
        report = diagnostics.report_for(context, root)
        if report is None:
            layout.label(text="Not checked", icon="INFO")
        elif (report.generation != ui_cache._versions["project"]
              or report.material_generation != ui_cache._versions["material"]):
            layout.label(text="Checks need refresh", icon="INFO")
        else:
            layout.label(text=f"Errors: {report.errors} | Warnings: {report.warnings}")
            layout.label(text=f"Needs Review: {report.reviews}")
            for line in textwrap.wrap(report.scope, width=30):
                layout.label(text=line)
        row = layout.row(align=True)
        row.operator("track_workshop.choose_project", text="Track", icon="FILE_FOLDER")
        row.prop(scene, "tw_project_pinned", text="", icon="PINNED" if scene.tw_project_pinned else "UNPINNED")
    else:
        layout.label(text="No active track project", icon="INFO")
    row = layout.row(align=True)
    for mode, label, icon in (("WORK", "Work", "SHADING_SOLID"), ("MATERIAL", "Materials", "SHADING_TEXTURE")):
        row.operator("track_workshop.preview_quality", text=label, icon=icon).mode = mode
    layout.prop(scene, "tw_workflow_stage", expand=True, icon_only=True)
    layout.label(text=dict((item[0], item[1]) for item in STAGES)[scene.tw_workflow_stage])
    if scene.tw_workflow_stage == "TRACK":
        layout.prop(scene, "tw_track_tab", text="Task")
    if scene.tw_job_running:
        for line in textwrap.wrap(scene.tw_job_label, width=30):
            layout.label(text=line)
        if hasattr(layout, "progress"):
            layout.progress(factor=scene.tw_job_progress, type="BAR", text=f"{scene.tw_job_progress*100:.0f}%")
        layout.operator("track_workshop.cancel_job", icon="CANCEL")


CLASSES = (TW_PG_view_flag, TW_PG_view_state, TW_OT_choose_project, TW_OT_work_view, TW_OT_preview_quality)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.tw_workflow_stage = EnumProperty(name="Task", items=STAGES, default="PROJECT")
    bpy.types.Scene.tw_track_tab = EnumProperty(name="Track Task", items=TRACK_TABS, default="MARKERS")
    bpy.types.Scene.tw_project_pinned = BoolProperty(name="Pin Project", default=False,
        description="Keep the chosen project active instead of following object selection")
    bpy.types.Scene.tw_expert = BoolProperty(name="Expert Details", default=False)
    bpy.types.Scene.tw_view_states = CollectionProperty(type=TW_PG_view_state)


def unregister():
    _project_items.clear()
    _project_strings.clear()
    for name in ("tw_workflow_stage", "tw_track_tab", "tw_project_pinned", "tw_expert", "tw_view_states"):
        delattr(bpy.types.Scene, name)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
