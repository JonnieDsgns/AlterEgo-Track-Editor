"""Explicit timing roles on existing marker pairs; no native F1 activation."""
import json
import textwrap

import bpy
from bpy.props import EnumProperty, PointerProperty

from . import marker_ui, rules, routes, timing_geometry, ui_cache

ROLES = (("UNASSIGNED", "Unassigned", "No timing function assigned"),
         ("START_FINISH", "Start / Finish", "Lap timing reference"),
         ("SECTOR_1", "Sector 1", "End of the first sector"),
         ("SECTOR_2", "Sector 2", "End of the second sector"))
LABELS = {role: label for role, label, _ in ROLES}
_syncing = False


def groups(root):
    result = {}
    for obj in root.all_objects:
        if obj.get("tw_is_marker") and obj.tw_marker.kind == "TIMING":
            result.setdefault(obj.tw_marker.number, []).append(obj)
    return dict(sorted(result.items()))


def endpoints(objects):
    left = [obj for obj in objects if obj.tw_marker.side == "LEFT"]
    right = [obj for obj in objects if obj.tw_marker.side == "RIGHT"]
    if len(left) != 1 or len(right) != 1 or len(objects) != 2:
        raise ValueError("Expected exactly one left and one right marker.")
    return left[0], right[0]


def role_changed(self, context):
    global _syncing
    ui_cache.invalidate("project")
    obj = self.id_data
    if _syncing or context is None or not obj.get("tw_is_marker") or obj.tw_marker.kind != "TIMING":
        return
    root = marker_ui.object_root(context, obj)
    if root is None or not root.is_editable:
        return
    try:
        pair = endpoints(groups(root).get(obj.tw_marker.number, []))
    except ValueError:
        return
    if not all(item.is_editable for item in pair):
        return
    _syncing = True
    try:
        for item in pair:
            if item != obj:
                item.tw_timing.role = self.role
    finally:
        _syncing = False


class TW_PG_timing(bpy.types.PropertyGroup):
    role: EnumProperty(name="Timing Role", items=ROLES, default="UNASSIGNED", update=role_changed)


def state(root):
    issues, gates = [], []

    def issue(message, objects=()):
        issues.append({"message": message, "objects": [obj.name for obj in objects], "severity": "ERROR"})

    try:
        main = rules.single_line(root, "RACING_LINE")
        vertices = routes.points(main)
    except ValueError as error:
        vertices = None
        issue(str(error))
    for number, objects in groups(root).items():
        label = f"Timing Gate {number}"
        roles = {obj.tw_timing.role for obj in objects}
        gate = {"number": number, "objects": objects, "role": None, "crossing": None}
        gates.append(gate)
        if len(roles) != 1:
            issue(label + ": endpoints have different timing roles.", objects)
        else:
            gate["role"] = next(iter(roles))
        try:
            left, right = endpoints(objects)
            if vertices is not None:
                gate["crossing"] = timing_geometry.crossing(vertices, tuple(left.matrix_world.translation),
                                                            tuple(right.matrix_world.translation))
        except ValueError as error:
            issue(label + ": " + str(error), objects)
    assigned = {}
    for role in ("START_FINISH", "SECTOR_1", "SECTOR_2"):
        matches = [gate for gate in gates if gate["role"] == role]
        if len(matches) != 1:
            issue(f"{LABELS[role]}: expected one gate, found {len(matches)}.",
                  [obj for gate in matches for obj in gate["objects"]])
        elif matches[0]["crossing"] is not None:
            assigned[role] = matches[0]
    if len(assigned) == 3:
        a, b, c = [assigned[role]["crossing"] for role in ("START_FINISH", "SECTOR_1", "SECTOR_2")]
        try:
            timing_geometry.sector_order(a["progress"], b["progress"], c["progress"], a["length"])
        except ValueError as error:
            issue(str(error), [obj for gate in assigned.values() for obj in gate["objects"]])
    return gates, issues


class TW_OT_check_timing(rules.ProjectOperator, bpy.types.Operator):
    bl_idname = "track_workshop.check_timing"
    bl_label = "Check Timing"

    def execute(self, context):
        context.view_layer.update()
        root = marker_ui.project(context)
        snapshot = ui_state(root)
        _, issues = snapshot
        ui_cache.put("timing", root, snapshot)
        self.report({"WARNING"} if issues else {"INFO"},
                    f"{len(issues)} timing warnings" if issues else "Timing checks passed")
        return {"FINISHED"}


def selection_button(layout, root, objects, text, icon="RESTRICT_SELECT_OFF", emboss=True):
    button = layout.operator("track_workshop.marker_select_issue", text=text, icon=icon, emboss=emboss)
    button.project_id = root["tw_project_id"]
    button.object_names = json.dumps([obj.name if isinstance(obj, bpy.types.Object) else obj for obj in objects])


def ui_state(root):
    gates, issues = state(root)
    for gate in gates:
        gate["objects"] = [obj.name for obj in gate["objects"]]
    return gates, issues


def ui_groups(root):
    result = []
    for number, objects in groups(root).items():
        roles = {obj.tw_timing.role for obj in objects}
        result.append({"number": number, "objects": [obj.name for obj in objects],
                       "role": next(iter(roles)) if len(roles) == 1 else None, "crossing": None})
    return result


class TW_PT_timing(bpy.types.Panel):
    bl_label = "Timing and Sectors"
    bl_idname = "TW_PT_timing"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AlterEgo Track Editor"

    @classmethod
    def poll(cls, context):
        from .workflow import stage
        return stage(context, "TRACK", "TIMING")

    def draw(self, context):
        layout = self.layout
        root = marker_ui.ui_project(context)
        if root is None:
            layout.label(text="No active track project", icon="INFO")
            return
        layout.operator("track_workshop.check_timing", icon="CHECKMARK")
        snapshot = ui_cache.get("timing", root, lambda: ui_state(root))
        if not ui_cache.ready(layout, snapshot):
            snapshot = (ui_cache.light("timing-groups", root, lambda: ui_groups(root)), [])
        gates, issues = snapshot
        start = [gate["crossing"] for gate in gates if gate["role"] == "START_FINISH" and gate["crossing"] is not None]
        for gate in ui_cache.page(layout, context.scene, gates, "gates"):
            selection_button(layout, root, gate["objects"], f"Timing Gate {gate['number']}", "EMPTY_SINGLE_ARROW")
            try:
                objects = [marker_ui.ui_object(root, name) for name in gate["objects"]]
                if any(obj is None for obj in objects):
                    continue
                left, right = endpoints(objects)
                row = layout.row()
                row.enabled = root.is_editable and left.is_editable and right.is_editable
                row.prop(left.tw_timing, "role", text="Role")
            except ValueError:
                pass
            if gate["crossing"] is not None:
                hit = gate["crossing"]
                if len(start) == 1:
                    progress = (hit["progress"]-start[0]["progress"]) % 1.0
                    layout.label(text=f"Lap: {progress*100:.2f}% | {progress*hit['length']:.1f} m")
                else:
                    layout.label(text=f"Line position: {hit['progress']*100:.2f}%")
        for issue in ui_cache.page(layout, context.scene, issues, "timing"):
            column = layout.column(align=True)
            for index, line in enumerate(textwrap.wrap(issue["message"], width=30)):
                if issue["objects"]:
                    selection_button(column, root, issue["objects"], line, "ERROR" if index == 0 else "NONE", False)
                else:
                    column.label(text=line, icon="ERROR" if index == 0 else "NONE")


CLASSES = (TW_PG_timing, TW_OT_check_timing, TW_PT_timing)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Object.tw_timing = PointerProperty(type=TW_PG_timing)


def unregister():
    del bpy.types.Object.tw_timing
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
