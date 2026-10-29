"""Marker editing in Blender; local +Z is forward for imported and new markers."""
import json
import math
import textwrap
import uuid
from collections import OrderedDict

import bpy
from bpy.props import EnumProperty, IntProperty, PointerProperty, StringProperty
from mathutils import Matrix

from .markers import TYPES, SIDES, LABELS, plan, validate, findings
from . import collection_layout, ui_cache


def kind_changed(self, context):
    ui_cache.invalidate("project")
    obj = self.id_data
    if context is not None and obj.get("tw_is_marker"):
        root = object_root(context, obj)
        if root is not None and root.get("tw_collection_layout_version"):
            collection_layout.place_marker(obj, root)


class TW_PG_marker(bpy.types.PropertyGroup):
    kind: EnumProperty(name="Type", items=TYPES, default="GRID", update=kind_changed)
    number: IntProperty(name="Number", default=1, min=1, max=2147483647, update=ui_cache.changed)
    side: EnumProperty(name="Side", items=SIDES, default="LEFT", update=ui_cache.changed)


def roots(context):
    return [collection for collection in context.scene.collection.children_recursive
            if collection.get("tw_project_id") and not collection.get("tw_import_pending")]


def object_root(context, obj):
    if obj is None:
        return None
    available = roots(context)
    identity = obj.get("tw_project_id")
    for root in available:
        if identity == root["tw_project_id"] and obj.name in root.all_objects:
            return root
    for root in available:
        if obj.name in root.all_objects:
            return root
    return None


def project(context):
    if getattr(context.scene, "tw_project_pinned", False) and context.scene.tw_marker_project in roots(context):
        return context.scene.tw_marker_project
    active = object_root(context, context.active_object)
    if active is not None:
        return active
    available = roots(context)
    chosen = context.scene.tw_marker_project
    if chosen in available:
        return chosen
    return available[0] if len(available) == 1 else None


def ui_roots(context):
    return ui_cache.light("project-roots", context.scene, lambda: roots(context))


def ui_object(root, name):
    return ui_cache.light("object-names", root, lambda: {obj.name: obj for obj in root.all_objects}).get(name)


def ui_object_root(context, obj):
    if obj is None:
        return None

    def build():
        collections = {}
        for root in ui_roots(context):
            for collection in (root, *root.children_recursive):
                entry = collections.setdefault(collection.as_pointer(), (collection, []))
                entry[1].append(root)
        return collections, OrderedDict()

    collections, objects = ui_cache.light("project-owners", context.scene, build)
    pointer = obj.as_pointer()
    if pointer not in objects:
        # Direct native lookups avoid both all_objects' recursive cache build and
        # users_collection's Python copies of every collection's object list.
        memberships = {root.as_pointer() for collection, roots in collections.values()
                       if collection.objects.get(obj.name) == obj for root in roots}
        objects[pointer] = tuple(root for root in ui_roots(context) if root.as_pointer() in memberships)
    objects.move_to_end(pointer)
    owners = objects[pointer]
    while len(objects) > 256:
        objects.popitem(last=False)
    identity = obj.get("tw_project_id")
    return next((root for root in owners if root.get("tw_project_id") == identity), owners[0] if owners else None)


def ui_project(context):
    available = ui_roots(context)
    chosen = context.scene.tw_marker_project
    if getattr(context.scene, "tw_project_pinned", False) and chosen in available:
        return chosen
    active = ui_object_root(context, context.active_object)
    if active is not None:
        return active
    return chosen if chosen in available else available[0] if len(available) == 1 else None


def marker_owner(obj):
    while obj is not None:
        if obj.get("tw_is_marker"):
            return obj
        target = obj.get("tw_marker_target")
        if isinstance(target, bpy.types.Object) and target.get("tw_is_marker"):
            return target
        if not obj.get("tw_marker_helper") and not obj.get("tw_marker_source_only"):
            break
        obj = obj.parent
    return None


def active_marker(context):
    return marker_owner(context.active_object)


def editable(obj):
    return obj is not None and obj.is_editable


def inventory(root):
    rows = []
    for obj in root.all_objects:
        if not obj.get("tw_is_marker"):
            continue
        state = obj.tw_marker
        rows.append({"name": obj.name, "type": state.kind, "number": state.number, "side": state.side,
                     "position": list(obj.matrix_world.translation),
                     "forward": list(obj.matrix_world.to_3x3().col[2])})
    return rows


def configure(obj, kind, number, side):
    obj["tw_is_marker"] = True
    obj["tw_marker_id"] = str(uuid.uuid4())
    obj["tw_marker_forward_axis"] = "Z"
    obj["tw_exclude_render_export"] = True
    obj.hide_render = True
    obj.show_in_front = True
    obj.tw_marker.kind = kind
    obj.tw_marker.number = number
    obj.tw_marker.side = side
    if obj.type == "EMPTY":
        obj.empty_display_type = "SINGLE_ARROW"
        obj.empty_display_size = 2.0
    if obj.type == "MESH":
        obj.tw_surface.collision = False
        obj.tw_surface.collision_manual = False


def import_model(context, root, objects, nodes):
    mapping = plan(nodes)
    collections = collection_layout.ensure(root)
    context.view_layer.update()
    authored = {}
    for index, marker in mapping["anchors"].items():
        source = objects[index]
        suffix = " " + marker["side"].title() if marker["type"] == "TIMING" else ""
        obj = bpy.data.objects.new(f"{LABELS[marker['type']]} {marker['number']}{suffix}", None)
        collections[marker["type"]].objects.link(obj)
        obj["tw_project_id"] = root["tw_project_id"]
        configure(obj, marker["type"], marker["number"], marker["side"])
        obj.matrix_world = source.matrix_world.copy()
        for key in ("tw_source_model", "tw_source_node", "tw_source_name", "tw_source_section", "tw_source_id"):
            obj[key] = source[key]
        obj["tw_marker_source"] = json.dumps(dict(marker, name=nodes[index]["name"], node=index,
                                                  forward_axis="Z"), sort_keys=True)
        authored[index] = obj
        source["tw_marker_source_only"] = True
        source["tw_marker_target"] = obj
        source["tw_exclude_render_export"] = True
        source.hide_render = True
        if source.type == "MESH":
            source.tw_surface.collision = False
            source.tw_surface.collision_manual = False
    for index, anchor in mapping["displays"].items():
        obj = objects[index]
        obj["tw_marker_helper"] = True
        obj["tw_marker_anchor_source_id"] = objects[anchor]["tw_source_id"]
        obj["tw_marker_target"] = authored[anchor]
        obj["tw_exclude_render_export"] = True
        obj.hide_render = True
        if obj.type == "MESH":
            obj.tw_surface.collision = False
            obj.tw_surface.collision_manual = False
    return mapping


class TW_OT_marker_add(bpy.types.Operator):
    bl_idname = "track_workshop.marker_add"
    bl_label = "Add Marker"
    bl_description = "Add a marker at the 3D cursor in the active track project"
    bl_options = {"REGISTER", "UNDO"}

    kind: EnumProperty(name="Type", items=TYPES, default="GRID")
    number: IntProperty(name="Number", default=1, min=1, max=2147483647)
    side: EnumProperty(name="Side", items=SIDES, default="LEFT")

    @classmethod
    def poll(cls, context):
        root = ui_project(context)
        return context.mode == "OBJECT" and root is not None and root.is_editable

    def invoke(self, context, event):
        numbers = [row["number"] for row in inventory(project(context)) if row["type"] == self.kind]
        self.number = max(numbers, default=0) + 1
        return context.window_manager.invoke_props_dialog(self, width=340)

    def draw(self, context):
        self.layout.prop(self, "kind")
        self.layout.prop(self, "number")
        if self.kind == "TIMING":
            self.layout.prop(self, "side")

    def execute(self, context):
        root = project(context)
        obj = bpy.data.objects.new(f"{LABELS[self.kind]} {self.number}", None)
        root.objects.link(obj)
        obj["tw_project_id"] = root["tw_project_id"]
        configure(obj, self.kind, self.number, self.side)
        collection_layout.place_marker(obj, root)
        # A new marker faces cursor-local +Y; its own +Z arrow is the forward axis.
        obj.matrix_world = context.scene.cursor.matrix @ Matrix.Rotation(-math.pi / 2, 4, "X")
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        context.view_layer.objects.active = obj
        return {"FINISHED"}


class TW_OT_marker_delete(bpy.types.Operator):
    bl_idname = "track_workshop.marker_delete"
    bl_label = "Delete Marker"
    bl_description = "Delete the active logical marker and its display helpers, keeping other children"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and editable(active_marker(context))

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        obj = active_marker(context)
        context.view_layer.update()
        helpers = [child for child in obj.children_recursive
                   if child.get("tw_marker_helper") and not child.get("tw_is_marker")
                   and marker_owner(child) == obj]
        deleting = set(helpers + [obj])
        for parent in deleting:
            for child in list(parent.children):
                if child not in deleting:
                    matrix = child.matrix_world.copy()
                    child.parent = obj.parent
                    child.matrix_world = matrix
        for child in helpers + [obj]:
            data = child.data if child.type == "MESH" else None
            bpy.data.objects.remove(child, do_unlink=True)
            if data is not None and data.users == 0:
                bpy.data.meshes.remove(data)
        return {"FINISHED"}


class TW_OT_marker_validate(bpy.types.Operator):
    bl_idname = "track_workshop.marker_validate"
    bl_label = "Check Markers"
    bl_description = "Check duplicate numbers, missing basic marker types, timing pairs and orientations"

    @classmethod
    def poll(cls, context):
        return ui_project(context) is not None

    def execute(self, context):
        root = project(context)
        context.view_layer.update()
        issues = validate(inventory(root))
        if root.is_editable:
            root["tw_marker_validation"] = json.dumps(issues)
        ui_cache.put("marker-findings", root, findings(inventory(root)))
        self.report({"WARNING"} if issues else {"INFO"},
                    f"{len(issues)} marker warnings" if issues else "Marker checks passed")
        return {"FINISHED"}


class TW_OT_marker_select_issue(bpy.types.Operator):
    bl_idname = "track_workshop.marker_select_issue"
    bl_label = "Select Affected Markers"
    bl_description = "Select the marker or markers affected by this warning"
    bl_options = {"UNDO"}

    object_names: StringProperty(options={"HIDDEN"})
    project_id: StringProperty(options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT"

    def execute(self, context):
        root = next((root for root in roots(context) if root["tw_project_id"] == self.project_id), None)
        try:
            names = json.loads(self.object_names)
        except (ValueError, TypeError):
            names = None
        if root is None or not isinstance(names, list) or not names or not all(isinstance(name, str) for name in names):
            self.report({"WARNING"}, "Marker warning is no longer available")
            return {"CANCELLED"}
        objects = [root.all_objects.get(name) for name in dict.fromkeys(names)]
        if any(obj is None or not obj.get("tw_is_marker") for obj in objects):
            self.report({"WARNING"}, "An affected marker has been renamed or removed")
            return {"CANCELLED"}
        if any(obj.name not in context.view_layer.objects or obj.hide_select
               or not obj.visible_get(view_layer=context.view_layer) for obj in objects):
            self.report({"WARNING"}, "Make the affected markers visible and selectable in this View Layer first")
            return {"CANCELLED"}
        for obj in context.selected_objects:
            obj.select_set(False)
        for obj in objects:
            obj.select_set(True)
        context.view_layer.objects.active = objects[0]
        return {"FINISHED"}


class TW_PT_markers(bpy.types.Panel):
    bl_label = "Markers"
    bl_idname = "TW_PT_markers"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AlterEgo Track Editor"

    @classmethod
    def poll(cls, context):
        from .workflow import stage
        return stage(context, "TRACK", "MARKERS")

    def draw(self, context):
        layout = self.layout
        root = ui_project(context)
        if ui_object_root(context, context.active_object) is None and len(ui_roots(context)) > 1:
            layout.prop(context.scene, "tw_marker_project", text="Track")
        elif root is not None:
            layout.label(text=root.name, icon="OUTLINER_COLLECTION")
        if root is None:
            layout.label(text="No active track project", icon="INFO")
            return
        obj = active_marker(context)
        if obj is not None and ui_object_root(context, obj) != root:
            obj = None
        if obj is not None:
            body = layout.column()
            body.enabled = editable(obj)
            body.label(text=obj.name, icon="EMPTY_SINGLE_ARROW")
            body.prop(obj.tw_marker, "kind")
            body.prop(obj.tw_marker, "number")
            if obj.tw_marker.kind == "TIMING":
                body.prop(obj.tw_marker, "side")
                body.prop(obj.tw_timing, "role")
            body.prop(obj, "location")
            body.prop(obj, "rotation_euler", text="Rotation")
            body.operator("track_workshop.marker_delete", icon="TRASH")
        else:
            layout.label(text="No active marker", icon="INFO")
        layout.operator("track_workshop.marker_add", icon="ADD")
        layout.operator("track_workshop.marker_validate", icon="CHECKMARK")
        issues = ui_cache.get("marker-findings", root, lambda: findings(inventory(root)))
        if not ui_cache.ready(layout, issues):
            return
        if issues:
            layout.label(text=f"{len(issues)} warnings", icon="ERROR")
            for issue in ui_cache.page(layout, context.scene, issues, "markers"):
                column = layout.column(align=True)
                # Short labels remain readable in a narrow sidebar.
                for index, line in enumerate(textwrap.wrap(issue["message"], width=30, break_long_words=True)):
                    if issue["objects"]:
                        button = column.operator("track_workshop.marker_select_issue", text=line, emboss=False,
                                                 icon="RESTRICT_SELECT_OFF" if index == 0 else "NONE")
                        button.object_names = json.dumps(issue["objects"])
                        button.project_id = root["tw_project_id"]
                    else:
                        column.label(text=line)


def project_poll(self, collection):
    return bool(collection.get("tw_project_id"))


CLASSES = (TW_PG_marker, TW_OT_marker_add, TW_OT_marker_delete, TW_OT_marker_validate,
           TW_OT_marker_select_issue, TW_PT_markers)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Object.tw_marker = PointerProperty(type=TW_PG_marker)
    bpy.types.Scene.tw_marker_project = PointerProperty(type=bpy.types.Collection, poll=project_poll)


def unregister():
    del bpy.types.Scene.tw_marker_project
    del bpy.types.Object.tw_marker
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
