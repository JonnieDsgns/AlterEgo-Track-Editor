"""Independent legal-boundary authoring and explicit pit-rule positions."""
import math
import textwrap

import bpy
from bpy.props import EnumProperty, FloatProperty, PointerProperty, StringProperty
from mathutils import Matrix, Vector

from . import ai, collection_layout, marker_ui, routes, rule_geometry, ui_cache

PIT_ROLES = (("ENTRY", "Pit Entry", "Start of the authored pit area"),
             ("LIMITER_START", "Speed Limiter Start", "Start of the speed-limited area"),
             ("LIMITER_END", "Speed Limiter End", "End of the speed-limited area"),
             ("EXIT", "Pit Exit", "End of the authored pit area"))
LABELS = {role: label for role, label, _ in PIT_ROLES}


class TW_PG_rules(bpy.types.PropertyGroup):
    speed_limit: FloatProperty(name="Speed Limit (km/h)", default=80, min=1, max=300)


def limits(root, side=None):
    return [obj for obj in root.all_objects if obj.get("tw_track_limit")
            and (side is None or obj.get("tw_limit_side") == side)]


def pit_rules(root, role=None):
    return [obj for obj in root.all_objects if obj.get("tw_pit_rule")
            and (role is None or obj.get("tw_pit_rule_role") == role)]


def ui_limits(root):
    return ui_cache.light("limits", root, lambda: limits(root))


def ui_pit_rules(root, role):
    return [obj for obj in ui_cache.light("pit-rules", root, lambda: pit_rules(root))
            if obj.get("tw_pit_rule_role") == role]


def single_line(root, kind):
    found = routes.lines(root, kind)
    if len(found) != 1:
        raise ValueError("Exactly one " + routes.LABELS[kind] + " is required.")
    obj = found[0]
    vertices = routes.points(obj)
    closed = kind == "RACING_LINE"
    if obj.data.splines[0].use_cyclic_u != closed:
        raise ValueError("Racing Line must be closed; Pit Line must be open.")
    ai.lengths(vertices, closed)
    return obj


def create_limits(context, root):
    ui_cache.invalidate("project")
    if limits(root):
        raise ValueError("Track limits already exist. Edit them; existing limits are never replaced.")
    main = single_line(root, "RACING_LINE")
    if main.get("tw_edges_input") != routes.fingerprint(main):
        raise ValueError("Update Racing Line road edges before creating track limits.")
    edges = [routes.helper(root, main, side) for side in ("LEFT", "RIGHT")]
    if any(edge is None for edge in edges):
        raise ValueError("Both Racing Line road edges are required.")
    if routes.edited_edges(root, main):
        raise ValueError("Road edges have manual edits. Rebuild them before creating track limits.")
    vertices = [routes.points(edge) for edge in edges]
    for edge, values in zip(edges, vertices):
        if not edge.data.splines[0].use_cyclic_u:
            raise ValueError("Road edges must be closed.")
        ai.lengths(values, True)
    target = collection_layout.ensure(root)["LEGAL_LIMITS"]
    for side, values in zip(("LEFT", "RIGHT"), vertices):
        obj = routes.curve(side.title() + " Track Limit", values, True, target,
                           (1, 0.15, 0.25, 1) if side == "LEFT" else (1, 0.85, 0.15, 1))
        obj["tw_track_limit"] = True
        obj["tw_limit_side"] = side
        obj["tw_project_id"] = root["tw_project_id"]
        obj["tw_limit_route"] = main
        obj["tw_limit_route_hash"] = routes.geometry_hash(main)
        obj["tw_limit_reviewed_geometry"] = ""
    context.view_layer.update()


def review_limits(root):
    ui_cache.invalidate("project")
    main = single_line(root, "RACING_LINE")
    found = []
    for side in ("LEFT", "RIGHT"):
        matches = limits(root, side)
        if len(matches) != 1:
            raise ValueError("Exactly one left and one right track limit are required.")
        obj = matches[0]
        if not obj.is_editable:
            raise ValueError("Track limits must be editable.")
        vertices = routes.points(obj)
        if not obj.data.splines[0].use_cyclic_u:
            raise ValueError("Track limits must be closed.")
        ai.lengths(vertices, True)
        found.append(obj)
    for obj in found:
        obj["tw_limit_route"] = main
        obj["tw_limit_route_hash"] = routes.geometry_hash(main)
        obj["tw_limit_reviewed_geometry"] = routes.geometry_hash(obj)


def set_pit_rule(context, root, role, progress):
    ui_cache.invalidate("project")
    pit = single_line(root, "PIT_LINE")
    position, direction = rule_geometry.at_progress(routes.points(pit), progress)
    matches = pit_rules(root, role)
    if len(matches) > 1:
        raise ValueError("Duplicate pit rule: remove the duplicate before setting this position.")
    obj = matches[0] if matches else None
    if obj is not None and (not obj.is_editable or obj.type != "EMPTY" or obj.constraints):
        raise ValueError("The pit-rule marker must be an editable Empty without constraints.")
    if obj is None:
        obj = bpy.data.objects.new(LABELS[role], None)
        collection_layout.ensure(root)["PIT_RULES"].objects.link(obj)
        obj["tw_pit_rule"] = True
        obj["tw_pit_rule_role"] = role
        obj["tw_project_id"] = root["tw_project_id"]
        obj["tw_exclude_render_export"] = True
        obj.hide_render = True
        obj.show_in_front = True
        obj.show_name = True
        obj.empty_display_type = "SINGLE_ARROW"
        obj.empty_display_size = 3
        obj.lock_location = obj.lock_rotation = obj.lock_scale = (True, True, True)
    obj.parent = None
    obj.matrix_world = Matrix.Translation(position) @ Vector(direction).to_track_quat("Z", "Y").to_matrix().to_4x4()
    obj["tw_rule_progress"] = progress
    obj["tw_rule_route"] = pit
    obj["tw_rule_route_hash"] = routes.geometry_hash(pit)
    context.view_layer.update()
    obj["tw_rule_matrix"] = [value for row in obj.matrix_world for value in row]
    return obj


def findings(root):
    result = []

    def issue(message, obj=None, severity="ERROR"):
        result.append({"message": message, "object": obj, "severity": severity})

    main = routes.lines(root, "RACING_LINE")
    for side in ("LEFT", "RIGHT"):
        matches = limits(root, side)
        if len(matches) != 1:
            issue(f"{side.title()} track limit: expected one, found {len(matches)}.", matches[0] if matches else None)
        for obj in matches:
            try:
                vertices = routes.points(obj)
                ai.lengths(vertices, True)
                if not obj.data.splines[0].use_cyclic_u:
                    issue(obj.name + ": track limit is not closed.", obj)
                if routes.geometry_hash(obj) != obj.get("tw_limit_reviewed_geometry"):
                    issue(obj.name + ": boundary needs review.", obj, "REVIEW")
                if (len(main) != 1 or obj.get("tw_limit_route") != main[0]
                        or obj.get("tw_limit_route_hash") != routes.geometry_hash(main[0])):
                    issue(obj.name + ": Racing Line changed; review the boundary.", obj, "REVIEW")
            except ValueError as error:
                issue(obj.name + ": " + str(error), obj)
    pit = routes.lines(root, "PIT_LINE")
    values = {}
    for role, label, _ in PIT_ROLES:
        matches = pit_rules(root, role)
        if len(matches) != 1:
            issue(f"{label}: expected one position, found {len(matches)}.", matches[0] if matches else None)
        for obj in matches:
            progress = obj.get("tw_rule_progress", -1)
            if not isinstance(progress, (int, float)) or not math.isfinite(progress) or not 0 <= progress <= 1:
                issue(label + ": invalid position.", obj)
                continue
            if len(matches) == 1:
                values[role] = progress
            try:
                if (len(pit) != 1 or obj.get("tw_rule_route") != pit[0]
                        or obj.get("tw_rule_route_hash") != routes.geometry_hash(pit[0])
                        or pit[0].data.splines[0].use_cyclic_u):
                    issue(label + ": Pit Line changed; set this position again.", obj, "REVIEW")
                saved = obj.get("tw_rule_matrix", [])
                actual = [value for row in obj.matrix_world for value in row]
                if len(saved) != 16 or any(abs(a-b) > 1e-5 for a, b in zip(saved, actual)):
                    issue(label + ": marker moved; set this position again.", obj, "REVIEW")
            except ValueError as error:
                issue(label + ": " + str(error), obj)
    for a, b in rule_geometry.order_issues(values):
        issue(LABELS[a] + " must precede " + LABELS[b] + ".", pit_rules(root, a)[0])
    try:
        single_line(root, "RACING_LINE")
        single_line(root, "PIT_LINE")
    except ValueError as error:
        issue(str(error))
    return result


def ui_findings(root):
    return [dict(issue, object=issue["object"].name if issue["object"] is not None else None)
            for issue in findings(root)]


class ProjectOperator:
    @classmethod
    def poll(cls, context):
        root = marker_ui.ui_project(context)
        return context.mode == "OBJECT" and root is not None and root.is_editable


class TW_OT_create_limits(ProjectOperator, bpy.types.Operator):
    bl_idname = "track_workshop.create_limits"
    bl_label = "Create Track Limits from Road Edges"
    bl_description = "Create independent editable boundary drafts; never replace existing track limits"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            context.view_layer.update()
            create_limits(context, marker_ui.project(context))
        except ValueError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class TW_OT_review_limits(ProjectOperator, bpy.types.Operator):
    bl_idname = "track_workshop.review_limits"
    bl_label = "Mark Track Limits Reviewed"
    bl_description = "Confirm your boundary review; checks basic geometry, not sporting legality or intersections"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        try:
            context.view_layer.update()
            review_limits(marker_ui.project(context))
        except ValueError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class TW_OT_pit_rule(ProjectOperator, bpy.types.Operator):
    bl_idname = "track_workshop.set_pit_rule"
    bl_label = "Set Pit Position"
    bl_description = "Explicitly position or re-confirm a pit rule on the current Pit Line"
    bl_options = {"REGISTER", "UNDO"}
    role: EnumProperty(name="Position", items=PIT_ROLES)
    method: EnumProperty(name="Position From", items=(("PERCENT", "Distance Along Pit Line", "Arc-length percentage"),
                                                     ("CURSOR", "3D Cursor", "Nearest segment projection"),
                                                     ("POINT", "Pit Line Point", "Point number in Lines and Road Widths")))
    percent: FloatProperty(name="Distance (%)", min=0, max=100, default=0)

    def invoke(self, context, event):
        matches = pit_rules(marker_ui.project(context), self.role)
        self.percent = matches[0].get("tw_rule_progress", 0)*100 if len(matches) == 1 else (100 if self.role == "EXIT" else 0)
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.prop(self, "role")
        self.layout.prop(self, "method")
        if self.method == "PERCENT":
            self.layout.prop(self, "percent")

    def execute(self, context):
        try:
            context.view_layer.update()
            root = marker_ui.project(context)
            pit = single_line(root, "PIT_LINE")
            vertices = routes.points(pit)
            progress = self.percent / 100
            if self.method == "CURSOR":
                nearest = ai.nearest(vertices, tuple(context.scene.cursor.location), False)
                progress = nearest["progress"]
                self.report({"INFO"}, f"Cursor projection distance: {nearest['distance']:.2f} m")
            elif self.method == "POINT":
                index = pit.tw_route.point-1
                if index >= len(vertices):
                    raise ValueError("Choose a valid Pit Line point number.")
                segments = ai.lengths(vertices, False)
                progress = sum(segments[:index]) / sum(segments)
            set_pit_rule(context, root, self.role, progress)
        except ValueError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}


class TW_OT_select_rule(ProjectOperator, bpy.types.Operator):
    bl_idname = "track_workshop.select_rule"
    bl_label = "Select Rule Object"
    bl_description = "Select the boundary or pit position without changing visibility or selection locks"
    bl_options = {"REGISTER", "UNDO"}
    object_name: StringProperty(options={"HIDDEN"})

    def execute(self, context):
        root = marker_ui.project(context)
        obj = root.all_objects.get(self.object_name)
        if (obj is None or obj.name not in context.view_layer.objects or not obj.visible_get()
                or obj.hide_select):
            self.report({"WARNING"}, "Object is hidden, locked or not in this view layer.")
            return {"CANCELLED"}
        for other in context.selected_objects:
            other.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        return {"FINISHED"}


class TW_OT_check_rules(ProjectOperator, bpy.types.Operator):
    bl_idname = "track_workshop.check_rules"
    bl_label = "Check Track and Pit Rules"

    def execute(self, context):
        context.view_layer.update()
        issues = findings(marker_ui.project(context))
        ui_cache.put("rule-findings", marker_ui.project(context),
                     [dict(issue, object=issue["object"].name if issue["object"] is not None else None) for issue in issues])
        self.report({"WARNING"} if issues else {"INFO"},
                    f"{len(issues)} rule warnings" if issues else "Basic rule checks passed")
        return {"FINISHED"}


class TW_PT_rules(bpy.types.Panel):
    bl_label = "Track Limits and Pit Rules"
    bl_idname = "TW_PT_rules"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AlterEgo Track Editor"

    @classmethod
    def poll(cls, context):
        from .workflow import stage
        return stage(context, "TRACK", "RULES")

    def draw(self, context):
        layout = self.layout
        root = marker_ui.ui_project(context)
        if root is None:
            layout.label(text="No active track project", icon="INFO")
            return
        layout.operator("track_workshop.create_limits", icon="CURVE_PATH")
        for obj in ui_cache.page(layout, context.scene, ui_limits(root), "limits"):
            layout.operator("track_workshop.select_rule", text=obj.name, icon="CURVE_PATH").object_name = obj.name
        layout.operator("track_workshop.review_limits", icon="CHECKMARK")
        layout.separator()
        layout.prop(root.tw_rules, "speed_limit")
        for role, label, _ in PIT_ROLES:
            matches = ui_pit_rules(root, role)
            row = layout.row(align=True)
            row.operator("track_workshop.set_pit_rule", text=label, icon="TRACKING").role = role
            if len(matches) == 1:
                obj = matches[0]
                row.operator("track_workshop.select_rule", text=f"{obj.get('tw_rule_progress', 0)*100:.1f}%",
                             icon="RESTRICT_SELECT_OFF").object_name = obj.name
        layout.operator("track_workshop.check_rules", icon="CHECKMARK")
        issues = ui_cache.get("rule-findings", root, lambda: ui_findings(root))
        for issue in ui_cache.page(layout, context.scene, issues, "rules") if ui_cache.ready(layout, issues) else ():
            column = layout.column(align=True)
            for index, line in enumerate(textwrap.wrap(issue["message"], width=30)):
                if issue["object"] is not None:
                    column.operator("track_workshop.select_rule", text=line, emboss=False,
                                    icon="ERROR" if index == 0 else "NONE").object_name = issue["object"]
                else:
                    column.label(text=line, icon="ERROR" if index == 0 else "NONE")


CLASSES = (TW_PG_rules, TW_OT_create_limits, TW_OT_review_limits, TW_OT_pit_rule,
           TW_OT_select_rule, TW_OT_check_rules, TW_PT_rules)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Collection.tw_rules = PointerProperty(type=TW_PG_rules)


def unregister():
    del bpy.types.Collection.tw_rules
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
