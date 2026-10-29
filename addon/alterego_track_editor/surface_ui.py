"""Persistent per-object physics assignments and their sidebar panel."""
import bpy
from bpy.props import BoolProperty, EnumProperty, PointerProperty

from .surfaces import SURFACES
from . import ui_cache


def surface_changed(self, context):
    self.surface_manual = True
    ui_cache.invalidate("project", structure=False)


def collision_changed(self, context):
    self.collision_manual = True
    ui_cache.invalidate("project", structure=False)


class TW_PG_surface(bpy.types.PropertyGroup):
    surface: EnumProperty(name="Assigned surface", items=SURFACES,
                          default="UNASSIGNED", update=surface_changed)
    collision: BoolProperty(name="Collision", default=False, update=collision_changed,
                            description="Include this mesh in the future collision export")
    surface_manual: BoolProperty(default=False, options={"HIDDEN"})
    collision_manual: BoolProperty(default=False, options={"HIDDEN"})


def editable(obj):
    return (obj is not None and obj.type == "MESH" and obj.is_editable
            and not obj.get("tw_is_marker") and not obj.get("tw_marker_helper")
            and not obj.get("tw_marker_source_only") and not obj.get("tw_is_route") and not obj.get("tw_route_helper")
            and not obj.get("tw_track_limit") and not obj.get("tw_pit_rule"))


class TW_OT_surface_to_selected(bpy.types.Operator):
    bl_idname = "track_workshop.surface_to_selected"
    bl_label = "Apply to Selected"
    bl_description = "Copy the active mesh's surface and collision setting to selected meshes"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return editable(context.active_object)

    def execute(self, context):
        source = context.active_object.tw_surface
        count = 0
        for obj in context.selected_objects:
            if obj == context.active_object or not editable(obj):
                continue
            obj.tw_surface.surface = source.surface
            obj.tw_surface.collision = source.collision
            count += 1
        self.report({"INFO"}, f"Updated {count} selected meshes")
        return {"FINISHED"}


class TW_OT_surface_reset(bpy.types.Operator):
    bl_idname = "track_workshop.surface_reset"
    bl_label = "Restore Import Assignment"
    bl_description = "Restore the active mesh's original surface suggestion and collision setting"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return editable(obj) and "tw_surface_suggestion" in obj

    def execute(self, context):
        obj = context.active_object
        obj.tw_surface.surface = obj["tw_surface_suggestion"]
        obj.tw_surface.collision = obj["tw_collision_suggestion"]
        obj.tw_surface.surface_manual = False
        obj.tw_surface.collision_manual = False
        return {"FINISHED"}


class TW_PT_surface(bpy.types.Panel):
    bl_label = "Surface"
    bl_idname = "TW_PT_surface"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AlterEgo Track Editor"

    @classmethod
    def poll(cls, context):
        from .workflow import stage, own_active
        return stage(context, "GEOMETRY") and own_active(context) and editable(context.active_object)

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            layout.label(text="No active mesh", icon="INFO")
            return
        if obj.get("tw_is_marker") or obj.get("tw_marker_helper") or obj.get("tw_marker_source_only"):
            layout.label(text="Marker helper", icon="EMPTY_SINGLE_ARROW")
            return
        if obj.get("tw_is_route") or obj.get("tw_route_helper") or obj.get("tw_track_limit") or obj.get("tw_pit_rule"):
            layout.label(text="Line helper", icon="CURVE_PATH")
            return
        layout.label(text=obj.name, icon="MESH_DATA")
        body = layout.column()
        body.enabled = editable(obj)
        body.prop(obj.tw_surface, "surface")
        body.prop(obj.tw_surface, "collision")
        if obj.tw_surface.surface_manual:
            label, icon = "Manually assigned", "CHECKMARK"
        elif obj.get("tw_surface_status") == "SUGGESTED":
            label, icon = "Imported suggestion", "INFO"
        elif not obj.tw_surface.collision:
            label, icon = "Visual only", "INFO"
        else:
            label, icon = "Needs review", "ERROR"
        body.label(text=label, icon=icon)
        if obj.tw_surface.collision and obj.tw_surface.surface == "UNASSIGNED":
            body.label(text="No surface assigned", icon="ERROR")
        body.operator("track_workshop.surface_to_selected", icon="COPYDOWN")
        if "tw_surface_suggestion" in obj:
            body.operator("track_workshop.surface_reset", icon="LOOP_BACK")


CLASSES = (TW_PG_surface, TW_OT_surface_to_selected, TW_OT_surface_reset, TW_PT_surface)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Object.tw_surface = PointerProperty(type=TW_PG_surface)


def unregister():
    del bpy.types.Object.tw_surface
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
