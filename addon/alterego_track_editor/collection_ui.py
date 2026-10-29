"""Prepare existing projects and assign independent assets to export variants."""
import bpy
from bpy.props import EnumProperty

from . import collection_layout, marker_ui
from .assets import move_asset, prepare_terrain


def prepare(context, root):
    context.view_layer.update()
    collections = collection_layout.ensure(root)
    source = collections["SOURCE"]
    for child in list(root.children):
        if child in (source, collections["EXPORT"]):
            continue
        if any(obj.get("tw_source_model") for obj in child.all_objects):
            if child.name not in source.children:
                source.children.link(child)
            root.children.unlink(child)
    for obj in list(root.objects):
        if not obj.get("tw_is_marker") and (obj.name.startswith("AC coordinates") or obj.get("tw_source_model")
                                            or any(child.get("tw_source_model") for child in obj.children_recursive)):
            collection_layout.move(obj, source, root)
    # Older projects used the original KN5 node as the editable marker. Retain
    # a source snapshot and move the existing authored object, preserving edits.
    markers = [obj for obj in root.all_objects if obj.get("tw_is_marker")]
    prepared = {obj.get("tw_marker_target") for obj in root.all_objects if obj.get("tw_marker_source_only")}
    legacy = [obj for obj in markers if obj.name not in collections["MARKUP"].all_objects and obj not in prepared]
    worlds = {obj: obj.matrix_world.copy() for obj in legacy}
    snapshots = {}
    parents = {obj: obj.parent for obj in legacy}
    for obj in legacy:
        if not obj.get("tw_marker_source"):
            continue
        snapshot = obj.copy()
        if obj.type == "MESH":
            snapshot.data = obj.data.copy()
        snapshot.name = obj.get("tw_source_name", obj.name) + " (AC source)"
        snapshot["tw_is_marker"] = False
        snapshot["tw_marker_source_only"] = True
        snapshot["tw_marker_target"] = obj
        source_collections = {source, *source.children_recursive}
        destinations = [collection for collection in obj.users_collection if collection in source_collections]
        for collection in destinations or [source]:
            collection.objects.link(snapshot)
        snapshots[obj] = snapshot
    for obj, snapshot in snapshots.items():
        snapshot.parent = snapshots.get(parents[obj], parents[obj])
        snapshot.matrix_world = worlds[obj]
        for child in list(obj.children):
            if child in markers:
                continue
            world = child.matrix_world.copy()
            child.parent = snapshot
            child.matrix_world = world
    for obj in legacy:
        obj.parent = None
        obj.matrix_world = worlds[obj]
        obj["tw_project_id"] = root["tw_project_id"]
    for obj in markers:
        collection_layout.place_marker(obj, root)
    root["tw_schema_version"] = max(3, root.get("tw_schema_version", 1))
    prepare_terrain(context, root, collections)
    return collections


class TW_OT_collection_setup(bpy.types.Operator):
    bl_idname = "track_workshop.collection_setup"
    bl_label = "Prepare Collections"
    bl_description = "Organize this project into separate AC Import and F1 Export collections"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        root = marker_ui.ui_project(context)
        return context.mode == "OBJECT" and root is not None and root.is_editable

    def execute(self, context):
        prepare(context, marker_ui.project(context))
        return {"FINISHED"}


class TW_OT_asset_assign(bpy.types.Operator):
    bl_idname = "track_workshop.asset_assign"
    bl_label = "Assign Selected Assets"
    bl_description = "Move existing assets into the export target without copying their data"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        root = marker_ui.ui_project(context)
        return context.mode == "OBJECT" and root is not None and root.is_editable

    def execute(self, context):
        root = marker_ui.project(context)
        selected = list(context.selected_objects)
        if not selected:
            self.report({"WARNING"}, "Select assets to assign first.")
            return {"CANCELLED"}
        collections = prepare(context, root)
        target = collections[context.scene.tw_asset_target]
        result = []
        context.view_layer.update()
        for obj in selected:
            owner = marker_ui.object_root(context, obj)
            if ((owner is not None and owner != root) or obj.type != "MESH" or not obj.is_editable
                    or obj.get("tw_is_marker") or obj.get("tw_marker_helper") or obj.get("tw_marker_source_only")):
                continue
            if obj.get("tw_is_route") or obj.get("tw_route_helper") or obj.get("tw_track_limit") or obj.get("tw_pit_rule"):
                continue
            asset = move_asset(obj, target, root)
            asset["tw_export_target"] = context.scene.tw_asset_target
            asset["tw_auto_terrain"] = False
            result.append(asset)
        if result:
            for obj in context.selected_objects:
                obj.select_set(False)
            for obj in result:
                obj.select_set(True)
            context.view_layer.objects.active = result[0]
        self.report({"INFO"}, f"Assigned {len(result)} assets; skipped {len(selected) - len(result)} objects")
        return {"FINISHED"}


class TW_PT_export_collections(bpy.types.Panel):
    bl_label = "F1 Export"
    bl_idname = "TW_PT_export_collections"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AlterEgo Track Editor"

    @classmethod
    def poll(cls, context):
        from .workflow import stage
        return stage(context, "GEOMETRY")

    def draw(self, context):
        layout = self.layout
        root = marker_ui.ui_project(context)
        if root is None:
            layout.label(text="No active track project", icon="INFO")
            return
        layout.label(text=root.name, icon="OUTLINER_COLLECTION")
        layout.operator("track_workshop.collection_setup", icon="OUTLINER_COLLECTION")
        layout.label(text="Asset Target")
        layout.prop(context.scene, "tw_asset_target", text="")
        layout.operator("track_workshop.asset_assign", icon="OUTLINER_COLLECTION")


CLASSES = (TW_OT_collection_setup, TW_OT_asset_assign, TW_PT_export_collections)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.tw_asset_target = EnumProperty(name="Target", items=collection_layout.ASSET_TARGETS,
                                                   default="COMMON_OBJECTS")


def unregister():
    del bpy.types.Scene.tw_asset_target
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
