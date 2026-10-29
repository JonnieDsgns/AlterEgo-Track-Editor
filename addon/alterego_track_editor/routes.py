"""Editable AC lines and width-derived draft road edges. No native race rules."""
import base64
import hashlib
import json
import math
import textwrap
from pathlib import Path

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty
from mathutils import Matrix, Vector

from . import ai, collection_layout, marker_ui, ui_cache

KINDS = (("RACING_LINE", "Racing Line", "Closed main line", 0),
         ("PIT_LINE", "Pit Line", "Open pit line", 1))
LABELS = {item[0]: item[1] for item in KINDS}


def width_changed(self, context):
    self.known = True
    ui_cache.invalidate("project", structure=False)


class TW_PG_width(bpy.types.PropertyGroup):
    left: FloatProperty(name="Left Width", min=0, max=1000, unit="LENGTH", update=width_changed)
    right: FloatProperty(name="Right Width", min=0, max=1000, unit="LENGTH", update=width_changed)
    normal: FloatVectorProperty(size=3, default=(0, 0, 1), update=ui_cache.content_changed)
    known: BoolProperty(default=False, update=ui_cache.content_changed)


class TW_PG_route(bpy.types.PropertyGroup):
    kind: EnumProperty(items=KINDS, default="RACING_LINE", update=ui_cache.changed)
    point: IntProperty(name="Point", min=1, default=1)
    widths: CollectionProperty(type=TW_PG_width)


def lines(root, kind=None):
    return [obj for obj in root.all_objects if obj.get("tw_is_route")
            and (kind is None or obj.tw_route.kind == kind)]


def ui_lines(root, kind=None):
    objects = ui_cache.light("routes", root, lambda: lines(root))
    return [obj for obj in objects if kind is None or obj.tw_route.kind == kind]


def active(context):
    obj = context.active_object
    if obj is not None and obj.get("tw_is_route"):
        return obj
    owner = obj.get("tw_route_owner") if obj is not None else None
    return owner if isinstance(owner, bpy.types.Object) and owner.get("tw_is_route") else None


def editable_route(context):
    obj, root = active(context), marker_ui.ui_project(context)
    return (obj is not None and obj.is_editable and root is not None and root.is_editable
            and marker_ui.ui_object_root(context, obj) == root)


def poly_spline(obj):
    if obj.type != "CURVE" or len(obj.data.splines) != 1 or obj.data.splines[0].type != "POLY":
        raise ValueError("Use a single Poly curve for the line.")
    if obj.modifiers or obj.constraints or obj.data.shape_keys is not None:
        raise ValueError("Use a Poly curve without modifiers, constraints or shape keys.")
    return obj.data.splines[0]


def points(obj):
    spline = poly_spline(obj)
    matrix = obj.matrix_world.copy()
    return [tuple(matrix @ point.co.xyz) for point in spline.points]


def summary(obj):
    vertices = points(obj)
    return sum(ai.lengths(vertices, obj.data.splines[0].use_cyclic_u))


def width_values(obj):
    return [(item.left, item.right) for item in obj.tw_route.widths]


def geometry_hash(obj):
    return hashlib.sha256(json.dumps([points(obj), obj.data.splines[0].use_cyclic_u]).encode()).hexdigest()


def fingerprint(obj):
    values = [[item.left, item.right, item.known, list(item.normal)] for item in obj.tw_route.widths]
    return hashlib.sha256((geometry_hash(obj) + json.dumps(values)).encode()).hexdigest()


def curve(name, vertices, closed, collection, color):
    data = bpy.data.curves.new(name, "CURVE")
    data.dimensions = "3D"
    data.bevel_depth = 0.065
    data.bevel_resolution = 0
    data.resolution_u = 1
    spline = data.splines.new("POLY")
    spline.points.add(len(vertices)-1)
    spline.points.foreach_set("co", [v for p in vertices for v in (*p, 1)])
    spline.use_cyclic_u = closed
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    obj.show_in_front = True
    obj.hide_render = True
    obj["tw_exclude_render_export"] = True
    material = bpy.data.materials.new(name + " Preview")
    material.diffuse_color = color
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = color
    shader.inputs["Emission Color"].default_value = color
    shader.inputs["Emission Strength"].default_value = 1
    data.materials.append(material)
    return obj


def helper(root, owner, role):
    return next((obj for obj in root.all_objects if obj.get("tw_route_owner") == owner
                 and obj.get("tw_route_helper_role") == role), None)


def set_helper(obj, owner, root, role):
    obj["tw_route_helper"] = True
    obj["tw_route_owner"] = owner
    obj["tw_project_id"] = root["tw_project_id"]
    obj["tw_route_helper_role"] = role
    obj["tw_exclude_render_export"] = True
    obj.hide_render = True
    obj.show_in_front = True


def edited_edges(root, obj):
    result = []
    for role in ("LEFT", "RIGHT"):
        edge = helper(root, obj, role)
        if edge is not None:
            try:
                changed = geometry_hash(edge) != edge.get("tw_generated_geometry")
            except ValueError:
                changed = True
            if changed:
                result.append(edge)
    return result


def update_edges(context, root, obj, replace=False):
    ui_cache.invalidate("project")
    vertices = points(obj)
    widths = obj.tw_route.widths
    if len(widths) != len(vertices) or any(not item.known for item in widths):
        raise ValueError("Set widths for all points before updating road edges.")
    closed = obj.data.splines[0].use_cyclic_u
    normal_matrix = obj.matrix_world.to_3x3().inverted()
    normal_matrix.transpose()
    left, right = ai.boundaries(vertices, width_values(obj),
                                [tuple(normal_matrix @ Vector(item.normal)) for item in widths], closed)
    if edited_edges(root, obj) and not replace:
        raise ValueError("Road edges were edited manually. Confirm replacement before rebuilding.")
    if any(edge is not None and edge.type != "CURVE" for edge in (helper(root, obj, "LEFT"), helper(root, obj, "RIGHT"))):
        raise ValueError("An edge was converted to another object type. Remove it before rebuilding.")
    for edge in (helper(root, obj, "LEFT"), helper(root, obj, "RIGHT")):
        if edge is not None and (edge.modifiers or edge.constraints or edge.data.shape_keys is not None):
            raise ValueError("Remove modifiers, constraints or shape keys from the edges before rebuilding.")
    collections = collection_layout.ensure(root)
    target = collections["ROAD_EDGES" if obj.tw_route.kind == "RACING_LINE" else "PIT_EDGES"]
    for role, values, color in (("LEFT", left, (0.12, 0.9, 0.15, 1)),
                                ("RIGHT", right, (1, 0.5, 0.03, 1))):
        edge = helper(root, obj, role)
        if edge is None:
            edge = curve(LABELS[obj.tw_route.kind] + " " + role.title() + " Edge (Draft)", values, closed, target, color)
            set_helper(edge, obj, root, role)
        else:
            if edge.data.users > 1:
                edge.data = edge.data.copy()
            edge.parent = None
            edge.matrix_world = Matrix.Identity(4)
            edge.data.splines.clear()
            spline = edge.data.splines.new("POLY")
            spline.points.add(len(values)-1)
            spline.points.foreach_set("co", [v for p in values for v in (*p, 1)])
            spline.use_cyclic_u = closed
    context.view_layer.update()
    for role in ("LEFT", "RIGHT"):
        edge = helper(root, obj, role)
        edge["tw_generated_geometry"] = geometry_hash(edge)
    obj["tw_edges_input"] = fingerprint(obj)
    update_direction(root, obj)


def update_direction(root, obj):
    vertices = points(obj)
    ai.lengths(vertices, obj.data.splines[0].use_cyclic_u)
    arrow = helper(root, obj, "DIRECTION")
    if arrow is None:
        arrow = bpy.data.objects.new(LABELS[obj.tw_route.kind] + " Direction", None)
        collection_layout.find(root, obj.tw_route.kind).objects.link(arrow)
        set_helper(arrow, obj, root, "DIRECTION")
        arrow.empty_display_type = "SINGLE_ARROW"
        arrow.empty_display_size = 4
    direction = Vector(vertices[1])-Vector(vertices[0])
    arrow.matrix_world = Matrix.Translation(vertices[0]) @ direction.to_track_quat("Z", "Y").to_matrix().to_4x4()


def connections(root):
    main, pit = lines(root, "RACING_LINE"), lines(root, "PIT_LINE")
    if len(main) != 1 or len(pit) != 1:
        return None
    main_points, pit_points = points(main[0]), points(pit[0])
    ai.lengths(pit_points, False)
    closed = main[0].data.splines[0].use_cyclic_u
    return {"entry": ai.nearest(main_points, pit_points[0], closed), "exit": ai.nearest(main_points, pit_points[-1], closed)}


def update_connections(context, root):
    ui_cache.invalidate("project")
    context.view_layer.update()
    result = connections(root)
    if result is None:
        return
    obj = lines(root, "PIT_LINE")[0]
    vertices = points(obj)
    collection = collection_layout.ensure(root)["PIT_CONNECTIONS"]
    for label, point, direction in (("entry", vertices[0], Vector(vertices[1])-Vector(vertices[0])),
                                     ("exit", vertices[-1], Vector(vertices[-1])-Vector(vertices[-2]))):
        role = "PIT_" + label.upper()
        marker = helper(root, obj, role)
        if marker is None:
            marker = bpy.data.objects.new("Pit " + label.title() + " (Draft)", None)
            collection.objects.link(marker)
            set_helper(marker, obj, root, role)
            marker.empty_display_type = "CIRCLE"
            marker.empty_display_size = 1.5
            marker.show_name = True
            marker.lock_location = (True, True, True)
            marker.lock_rotation = (True, True, True)
            marker.lock_scale = (True, True, True)
        marker.matrix_world = Matrix.Translation(point) @ direction.to_track_quat("Z", "Y").to_matrix().to_4x4()
        marker["tw_connection_progress"] = result[label]["progress"]
        marker["tw_connection_gap"] = result[label]["distance"]
        marker["tw_connection_review_required"] = True


def import_lines(context, root, folder, layout):
    collections = collection_layout.ensure(root)
    report = []
    warnings = []
    for kind, path in ai.files(folder, layout):
        if lines(root, kind):
            continue
        if not path.is_file():
            report.append(LABELS[kind] + ": AC file missing.")
            continue
        try:
            payload = path.read_bytes()
            data = ai.parse(payload)
        except (OSError, ValueError) as error:
            message = path.name + ": " + str(error).replace("KN5", "AC AI")
            report.append(message)
            warnings.append(message)
            continue
        rows = data["points"]
        if kind == "RACING_LINE" and len(rows) > 3 and math.dist(rows[0]["position"], rows[-1]["position"]) < 1e-5:
            rows = rows[:-1]
        vertices = [ai.blender_position(row["position"]) for row in rows]
        obj = curve(LABELS[kind], vertices, kind == "RACING_LINE", collections[kind],
                    (0.03, 0.7, 1, 1) if kind == "RACING_LINE" else (0.9, 0.15, 0.65, 1))
        obj["tw_is_route"] = True
        obj["tw_project_id"] = root["tw_project_id"]
        obj.tw_route.kind = kind
        text = bpy.data.texts.new(LABELS[kind] + " AC Source")
        text.use_fake_user = True
        # Blender's text editor is very slow with megabyte-long single lines.
        text.from_string(json.dumps({"path": str(path), "sha256": hashlib.sha256(payload).hexdigest(),
                                     "encoding": "base64", "data": base64.encodebytes(payload).decode("ascii").splitlines()},
                                    indent=2))
        obj["tw_route_source"] = text
        obj["tw_route_source_path"] = str(path)
        for row in rows:
            hint = row.get("hints", {})
            item = obj.tw_route.widths.add()
            l, r = hint.get("side_left", 0), hint.get("side_right", 0)
            item.left, item.right = max(0, l), max(0, r)
            item.normal = ai.blender_position([hint.get("normal_x", 0), hint.get("normal_y", 1), hint.get("normal_z", 0)])
            item.known = 0 < l <= 1000 and 0 < r <= 1000
        context.view_layer.update()
        try:
            update_direction(root, obj)
            update_edges(context, root, obj)
        except ValueError as error:
            report.append(LABELS[kind] + ": " + str(error))
    root["tw_route_import_report"] = json.dumps(report)
    try:
        update_connections(context, root)
    except ValueError as error:
        report.append("Pit connections: " + str(error))
        root["tw_route_import_report"] = json.dumps(report)
    return warnings


def findings(root):
    issues = []

    def add(message, kind, severity="ERROR"):
        issues.append({"message": message, "kind": kind, "severity": severity})

    for kind in LABELS:
        found = lines(root, kind)
        if not found:
            add("Missing " + LABELS[kind].lower() + ".", kind)
        if len(found) > 1:
            add("Multiple " + LABELS[kind].lower() + " objects.", kind)
        for obj in found:
            try:
                vertices = points(obj)
                closed = obj.data.splines[0].use_cyclic_u
                values = ai.lengths(vertices, closed)
                if closed != (kind == "RACING_LINE"):
                    add(obj.name + ": check open/closed state.", kind)
                if max(values) > max(50, 10*sorted(values)[len(values)//2]):
                    add(obj.name + ": unusually long segment; check for jumps.", kind, "WARNING")
                if len(obj.tw_route.widths) != len(vertices):
                    add(obj.name + ": point count changed; reset widths for all points.", kind)
                elif any(not item.known or item.left <= 0 or item.right <= 0 for item in obj.tw_route.widths):
                    add(obj.name + ": missing or invalid widths.", kind, "REVIEW")
                elif obj.get("tw_edges_input") != fingerprint(obj):
                    add(obj.name + ": road edges need updating.", kind, "REVIEW")
                if edited_edges(root, obj):
                    add(obj.name + ": road edges edited independently; review widths and edges together.", kind, "REVIEW")
            except ValueError as error:
                add(obj.name + ": " + str(error), kind)
    try:
        result = connections(root)
        if result:
            for key, value in result.items():
                if value["distance"] > 30:
                    add(f"Pit {key}: {value['distance']:.1f} m from racing line; review connection.", "PIT_LINE", "REVIEW")
    except ValueError:
        pass
    return issues


def check(root):
    return [item["message"] for item in findings(root)]


class TW_OT_select_line(bpy.types.Operator):
    bl_idname = "track_workshop.select_line"
    bl_label = "Select Line"
    bl_description = "Select the affected line in Object Mode"
    bl_options = {"UNDO"}
    kind: EnumProperty(items=KINDS, default="RACING_LINE")

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and marker_ui.ui_project(context) is not None

    def execute(self, context):
        objects = lines(marker_ui.project(context), self.kind)
        if not objects or any(obj.name not in context.view_layer.objects or not obj.visible_get()
                              or obj.hide_select for obj in objects):
            self.report({"WARNING"}, "The line is missing or not visible/selectable in this View Layer")
            return {"CANCELLED"}
        for obj in context.selected_objects:
            obj.select_set(False)
        for obj in objects:
            obj.select_set(True)
        context.view_layer.objects.active = objects[0]
        return {"FINISHED"}


class TW_OT_import_lines(bpy.types.Operator):
    bl_idname = "track_workshop.import_lines"
    bl_label = "Import AC Lines"
    bl_description = "Import missing lines from this layout without replacing existing edits"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        root = marker_ui.ui_project(context)
        return context.mode == "OBJECT" and root is not None and root.is_editable

    def execute(self, context):
        from .source import layouts
        root = marker_ui.project(context)
        before = len(lines(root))
        try:
            selected = next(row for row in layouts(root["tw_track_folder"]) if row["id"] == root["tw_layout_manifest"])
            warnings = import_lines(context, root, root["tw_track_folder"], selected["layout"])
        except (KeyError, StopIteration, OSError, ValueError) as error:
            self.report({"ERROR"}, "AC source unavailable: " + str(error))
            return {"CANCELLED"}
        total = len(lines(root))
        self.report({"WARNING"} if warnings or not total else {"INFO"},
                    f"Imported {total-before} lines; {total} total. Existing edits preserved.")
        return {"FINISHED"}


class TW_OT_widths(bpy.types.Operator):
    bl_idname = "track_workshop.set_widths"
    bl_label = "Set Widths"
    bl_description = "Set left/right distances for all points or the selected points in Edit Mode"
    bl_options = {"REGISTER", "UNDO"}
    left: FloatProperty(name="Left Width", min=0.01, max=1000, default=5, unit="LENGTH")
    right: FloatProperty(name="Right Width", min=0.01, max=1000, default=5, unit="LENGTH")
    selected_only: BoolProperty(name="Selected Points Only", default=False)

    @classmethod
    def poll(cls, context):
        obj = active(context)
        return obj is not None and obj.is_editable

    def invoke(self, context, event):
        self.selected_only = context.mode == "EDIT_CURVE"
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        obj = active(context)
        try:
            vertices = points(obj)
        except ValueError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        widths = obj.tw_route.widths
        if self.selected_only and len(widths) != len(vertices):
            self.report({"ERROR"}, "Reset widths for all points after changing topology")
            return {"CANCELLED"}
        if len(widths) != len(vertices):
            widths.clear()
            for _ in vertices:
                widths.add()
        for index, point in enumerate(obj.data.splines[0].points):
            if not self.selected_only or point.select:
                widths[index].left, widths[index].right = self.left, self.right
                widths[index].known = True
        return {"FINISHED"}


class TW_OT_use_curve(bpy.types.Operator):
    bl_idname = "track_workshop.use_route_curve"
    bl_label = "Use Selected Curve"
    bl_description = "Use a single Poly curve as a manual racing or pit line; no source AI file is changed"
    bl_options = {"REGISTER", "UNDO"}
    kind: EnumProperty(name="Line Type", items=KINDS, default="RACING_LINE")

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        root = marker_ui.ui_project(context)
        return (context.mode == "OBJECT" and root is not None and root.is_editable and obj is not None
                and obj.type == "CURVE" and obj.is_editable and not obj.get("tw_is_route")
                and not obj.get("tw_route_helper"))

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        root, obj = marker_ui.project(context), context.active_object
        try:
            if lines(root, self.kind):
                raise ValueError("This project already has that line type.")
            ai.lengths(points(obj), self.kind == "RACING_LINE")
        except ValueError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        world = obj.matrix_world.copy()
        if obj.data.users > 1:
            obj.data = obj.data.copy()
        collection_layout.move(obj, collection_layout.ensure(root)[self.kind], root)
        obj.parent = None
        obj.matrix_world = world
        obj["tw_is_route"] = True
        obj["tw_project_id"] = root["tw_project_id"]
        obj["tw_exclude_render_export"] = True
        obj.hide_render = True
        obj.show_in_front = True
        obj.tw_route.kind = self.kind
        obj.data.splines[0].use_cyclic_u = self.kind == "RACING_LINE"
        obj.tw_route.widths.clear()
        for _ in obj.data.splines[0].points:
            obj.tw_route.widths.add()
        context.view_layer.update()
        update_direction(root, obj)
        return {"FINISHED"}


class TW_OT_route_point(bpy.types.Operator):
    bl_idname = "track_workshop.route_point"
    bl_label = "Select Point"
    bl_description = "Select this control point in Edit Mode, or inspect the first selected point's widths"
    bl_options = {"REGISTER", "UNDO"}
    inspect_selection: BoolProperty(default=False, options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        obj = active(context)
        return obj is not None and obj.is_editable and obj.type == "CURVE"

    def execute(self, context):
        obj = active(context)
        try:
            vertices = points(obj)
            if self.inspect_selection:
                selected = [i for i, point in enumerate(obj.data.splines[0].points) if point.select]
                if not selected:
                    raise ValueError("No control point selected.")
                obj.tw_route.point = selected[0]+1
            else:
                if context.mode != "OBJECT":
                    raise ValueError("Select a point by number from Object Mode.")
                index = obj.tw_route.point-1
                if index >= len(vertices):
                    raise ValueError("Point number is outside the line.")
                for other in context.selected_objects:
                    other.select_set(False)
                obj.select_set(True)
                context.view_layer.objects.active = obj
                for i, point in enumerate(obj.data.splines[0].points):
                    point.select = i == index
                bpy.ops.object.mode_set(mode="EDIT")
        except ValueError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class TW_OT_remove_line(bpy.types.Operator):
    bl_idname = "track_workshop.remove_line"
    bl_label = "Remove Line"
    bl_description = "Remove this authoring line and its helpers; the packed AC source and original file remain intact"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = active(context)
        return context.mode == "OBJECT" and editable_route(context)

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        obj = active(context)
        root = marker_ui.project(context)
        context.view_layer.update()
        removing = [item for item in root.all_objects if item.get("tw_route_owner") == obj] + [obj]
        for item in removing:
            for child in list(item.children):
                if child not in removing:
                    matrix = child.matrix_world.copy()
                    child.parent = obj.parent
                    child.matrix_world = matrix
        for item in removing:
            data, kind = item.data, item.type
            bpy.data.objects.remove(item, do_unlink=True)
            if data is not None and data.users == 0:
                if kind == "CURVE":
                    bpy.data.curves.remove(data)
                elif kind == "MESH":
                    bpy.data.meshes.remove(data)
        return {"FINISHED"}


class TW_OT_edges(bpy.types.Operator):
    bl_idname = "track_workshop.update_edges"
    bl_label = "Update Road Edges"
    bl_description = "Rebuild draft edges from current geometry and widths in Object Mode"
    bl_options = {"REGISTER", "UNDO"}
    replace_edited: BoolProperty(name="Replace Manually Edited Edges", default=False)

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and editable_route(context)

    def invoke(self, context, event):
        root = marker_ui.project(context)
        if edited_edges(root, active(context)):
            return context.window_manager.invoke_props_dialog(self, width=380)
        return self.execute(context)

    def execute(self, context):
        try:
            context.view_layer.update()
            update_edges(context, marker_ui.project(context), active(context), self.replace_edited)
            update_connections(context, marker_ui.project(context))
        except ValueError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class TW_OT_connections(bpy.types.Operator):
    bl_idname = "track_workshop.pit_connections"
    bl_label = "Update Pit Connections"
    bl_description = "Refresh draft pit endpoints and nearest-line projections; does not create native pit rules"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        root = marker_ui.ui_project(context)
        return context.mode == "OBJECT" and root is not None and root.is_editable

    def execute(self, context):
        try:
            update_connections(context, marker_ui.project(context))
        except ValueError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class TW_OT_route_order(bpy.types.Operator):
    bl_idname = "track_workshop.route_order"
    bl_label = "Change Line Order"
    bl_description = "Reverse driving direction, or use the chosen point as lap start; road edges become stale"
    bl_options = {"REGISTER", "UNDO"}
    action: EnumProperty(items=(("REVERSE", "Reverse", "Reverse and swap left/right widths"),
                               ("START", "Set Lap Start", "Use the chosen point as the first point")))

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and editable_route(context)

    def execute(self, context):
        obj = active(context)
        try:
            vertices = points(obj)
            if len(vertices) != len(obj.tw_route.widths):
                raise ValueError("Reset widths after changing point count.")
            if self.action == "START" and not obj.data.splines[0].use_cyclic_u:
                raise ValueError("Lap start is only available for closed lines.")
            if self.action == "START" and obj.tw_route.point > len(vertices):
                raise ValueError("Choose a point number within the line's point count.")
        except ValueError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        count = len(vertices)
        start = min(obj.tw_route.point-1, count-1)
        order = list(reversed(range(count))) if self.action == "REVERSE" else list(range(start, count))+list(range(start))
        if self.action == "REVERSE" and obj.data.splines[0].use_cyclic_u:
            order = [0] + list(reversed(range(1, count)))
        coordinates = [tuple(point.co) for point in obj.data.splines[0].points]
        widths = [(item.left, item.right, item.known, tuple(item.normal)) for item in obj.tw_route.widths]
        obj.data.splines[0].points.foreach_set("co", [v for index in order for v in coordinates[index]])
        for dest, index in enumerate(order):
            l, r, known, normal = widths[index]
            item = obj.tw_route.widths[dest]
            item.left, item.right = (r, l) if self.action == "REVERSE" else (l, r)
            item.known, item.normal = known, normal
        obj.tw_route.point = 1
        context.view_layer.update()
        update_direction(marker_ui.project(context), obj)
        return {"FINISHED"}


class TW_OT_check_lines(bpy.types.Operator):
    bl_idname = "track_workshop.check_lines"
    bl_label = "Check Lines"

    @classmethod
    def poll(cls, context):
        return marker_ui.ui_project(context) is not None

    def execute(self, context):
        context.view_layer.update()
        root = marker_ui.project(context)
        findings_now = findings(root)
        issues = [item["message"] for item in findings_now]
        ui_cache.put("line-findings", root, findings_now)
        try:
            ui_cache.put("pit-connections", root, connections(root) or {})
            obj = active(context)
            if obj is not None:
                ui_cache.put("line-length", obj, summary(obj))
        except ValueError:
            pass
        self.report({"WARNING"} if issues else {"INFO"}, f"{len(issues)} line warnings" if issues else "Line checks passed")
        return {"FINISHED"}


class TW_PT_routes(bpy.types.Panel):
    bl_label = "Lines and Road Widths"
    bl_idname = "TW_PT_routes"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AlterEgo Track Editor"

    @classmethod
    def poll(cls, context):
        from .workflow import stage
        return stage(context, "TRACK", "LINES")

    def draw(self, context):
        layout = self.layout
        root = marker_ui.ui_project(context)
        if root is None:
            layout.label(text="No active track project", icon="INFO")
            return
        layout.operator("track_workshop.import_lines", icon="IMPORT")
        layout.operator("track_workshop.use_route_curve", icon="CURVE_PATH")
        for kind, label in LABELS.items():
            if ui_lines(root, kind):
                layout.operator("track_workshop.select_line", text=label, icon="CURVE_PATH").kind = kind
        obj = active(context)
        if obj is not None and marker_ui.ui_object_root(context, obj) != root:
            obj = None
        if obj is not None:
            layout.label(text=LABELS[obj.tw_route.kind], icon="CURVE_PATH")
            try:
                spline = poly_spline(obj)
                count = len(spline.points)
                distance = ui_cache.get("line-length", obj, lambda: summary(obj))
                if distance is None:
                    layout.label(text=f"{count} points")
                elif ui_cache.ready(layout, distance):
                    layout.label(text=f"{count} points | {distance:.1f} m")
                layout.prop(obj.data.splines[0], "use_cyclic_u", text="Closed Line")
                layout.prop(obj.tw_route, "point")
                if context.mode == "EDIT_CURVE":
                    layout.operator("track_workshop.route_point", text="Use Selected Point", icon="EYEDROPPER").inspect_selection = True
                else:
                    layout.operator("track_workshop.route_point", icon="RESTRICT_SELECT_OFF")
                index = obj.tw_route.point-1
                if index < len(obj.tw_route.widths):
                    item = obj.tw_route.widths[index]
                    layout.prop(item, "left")
                    layout.prop(item, "right")
                    if not item.known:
                        layout.label(text="Width not supplied", icon="ERROR")
                layout.operator("track_workshop.set_widths", icon="ARROW_LEFTRIGHT")
                layout.operator("track_workshop.update_edges", icon="FILE_REFRESH")
                layout.operator("track_workshop.route_order", text="Reverse Direction", icon="ARROW_LEFTRIGHT").action = "REVERSE"
                if obj.tw_route.kind == "RACING_LINE":
                    layout.operator("track_workshop.route_order", text="Set Lap Start", icon="TRACKING").action = "START"
            except ValueError as error:
                layout.label(text=str(error), icon="ERROR")
            layout.operator("track_workshop.remove_line", icon="TRASH")
        layout.operator("track_workshop.check_lines", icon="CHECKMARK")
        layout.operator("track_workshop.pit_connections", icon="FILE_REFRESH")
        issues = ui_cache.get("line-findings", root, lambda: findings(root))
        for issue in ui_cache.page(layout, context.scene, issues, "lines") if ui_cache.ready(layout, issues) else ():
            column = layout.column(align=True)
            for index, line in enumerate(textwrap.wrap(issue["message"], width=30)):
                if ui_lines(root, issue["kind"]):
                    button = column.operator("track_workshop.select_line", text=line, emboss=False,
                                             icon="RESTRICT_SELECT_OFF" if index == 0 else "NONE")
                    button.kind = issue["kind"]
                else:
                    column.label(text=line)
        try:
            result = ui_cache.get("pit-connections", root, lambda: connections(root) or {})
            if isinstance(result, dict) and result:
                for label, data in result.items():
                    layout.label(text=f"Pit {label}: {data['distance']:.1f} m / {100*data['progress']:.1f}%")
        except ValueError:
            pass


CLASSES = (TW_PG_width, TW_PG_route, TW_OT_select_line, TW_OT_import_lines, TW_OT_widths, TW_OT_use_curve, TW_OT_edges, TW_OT_connections,
           TW_OT_route_point, TW_OT_remove_line, TW_OT_route_order, TW_OT_check_lines, TW_PT_routes)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Object.tw_route = bpy.props.PointerProperty(type=TW_PG_route)


def unregister():
    del bpy.types.Object.tw_route
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
