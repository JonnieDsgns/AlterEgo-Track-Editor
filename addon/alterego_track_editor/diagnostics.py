"""Explicit, scoped project review with a persistent structured report."""
import json
import textwrap

import bpy
from bpy.app.handlers import persistent
from bpy.props import CollectionProperty, EnumProperty, IntProperty, PointerProperty, StringProperty

from . import marker_ui, routes, rules, timing, materials, surface_ui, workflow, jobs, ui_cache
from .markers import findings as marker_findings

CATEGORIES = (("ALL", "All Areas", "All supported checks"), ("SURFACES", "Surfaces", "Physical surface assignments"),
              ("MARKERS", "Markers", "Marker slots and orientations"), ("LINES", "Lines", "Geometry and widths"),
              ("RULES", "Limits and Pit Rules", "Boundaries and pit events"), ("TIMING", "Timing", "Lap and sectors"),
              ("MATERIALS", "Materials", "Static material source contracts"))
SEVERITIES = (("ALL", "All", "All findings"), ("ERROR", "Errors", "Invalid or missing data"),
              ("WARNING", "Warnings", "Potential problems"), ("REVIEW", "Needs Review", "Requires an authoring decision"))
LABELS = {item[0]: item[1] for item in CATEGORIES}


class TW_PG_issue(bpy.types.PropertyGroup):
    severity: StringProperty()
    category: StringProperty()
    message: StringProperty()
    targets: StringProperty()


class TW_PG_report(bpy.types.PropertyGroup):
    project: PointerProperty(type=bpy.types.Collection)
    issues: CollectionProperty(type=TW_PG_issue)
    scope: StringProperty()
    generation: IntProperty(default=-1)
    material_generation: IntProperty(default=-1)
    errors: IntProperty()
    warnings: IntProperty()
    reviews: IntProperty()


def report_for(context, root):
    return next((report for report in context.scene.tw_reports if report.project == root), None)


def normalize(category, message, objects=(), severity="WARNING"):
    return {"category": category, "message": message, "objects": list(dict.fromkeys(objects)), "severity": severity}


def collect_steps(context, root, scope, category, selected):
    """Only reads Blender data; cancellation leaves the previous report intact."""
    selected = set(selected)
    if scope == "SELECTED" and not selected:
        raise ValueError("Select objects in the active project first.")
    categories = [category] if category != "ALL" else [item[0] for item in CATEGORIES[1:]]
    if scope == "SELECTED":
        relevant = set()
        for name in list(selected):
            obj = root.all_objects.get(name)
            if obj is None:
                continue
            marker = marker_ui.marker_owner(obj)
            if marker is not None:
                selected.add(marker.name)
                relevant.add("MARKERS")
                if marker.tw_marker.kind == "TIMING":
                    relevant.add("TIMING")
                    selected.update(item.name for item in timing.groups(root).get(marker.tw_marker.number, []))
            owner = obj.get("tw_route_owner")
            if isinstance(owner, bpy.types.Object):
                selected.add(owner.name)
            if obj.get("tw_is_route") or obj.get("tw_route_helper"):
                relevant.update(("LINES", "RULES", "TIMING"))
            if obj.get("tw_track_limit") or obj.get("tw_pit_rule"):
                relevant.add("RULES")
            if surface_ui.editable(obj):
                relevant.update(("SURFACES", "MATERIALS"))
        categories = [name for name in categories if name in relevant]
    output, model_cache = [], {}

    def add(issue):
        if scope != "SELECTED" or selected.intersection(issue["objects"]):
            output.append(issue)

    objects = list(root.all_objects)
    for index, name in enumerate(categories):
        yield index/max(1, len(categories)), LABELS[name]
        if name == "MARKERS":
            for issue in marker_findings(marker_ui.inventory(root)):
                add(normalize(name, issue["message"], issue["objects"], issue.get("severity", "WARNING")))
        elif name == "LINES":
            for issue in routes.findings(root):
                add(normalize(name, issue["message"], [obj.name for obj in routes.lines(root, issue["kind"])], issue.get("severity", "WARNING")))
        elif name == "RULES":
            for issue in rules.findings(root):
                add(normalize(name, issue["message"], [issue["object"].name] if issue["object"] is not None else [], issue.get("severity", "WARNING")))
        elif name == "TIMING":
            for issue in timing.state(root)[1]:
                add(normalize(name, issue["message"], issue["objects"], issue.get("severity", "WARNING")))
        elif name == "SURFACES":
            for number, obj in enumerate(objects):
                if surface_ui.editable(obj) and obj.tw_surface.collision and obj.tw_surface.surface == "UNASSIGNED":
                    add(normalize(name, obj.name + ": no physical surface assigned.", [obj.name], "REVIEW"))
                if number % 100 == 0:
                    yield (index+number/max(1, len(objects)))/max(1, len(categories)), "Surfaces"
        elif name == "MATERIALS":
            used = {}
            for obj in objects:
                if obj.type == "MESH" and not any(obj.get(flag) for flag in ui_cache.AUTHORING_FLAGS):
                    for slot in obj.material_slots:
                        if slot.material is not None:
                            used.setdefault(slot.material, []).append(obj.name)
            for number, (material, names) in enumerate(used.items()):
                if scope == "SELECTED" and not selected.intersection(names):
                    continue
                try:
                    data, textures, warnings = materials.inventory(material, model_cache)
                except (ValueError, KeyError, TypeError) as error:
                    add(normalize(name, material.name + ": invalid source contract: " + str(error), names, "ERROR"))
                    continue
                if data is None:
                    add(normalize(name, material.name + ": source not captured.", names, "REVIEW"))
                else:
                    for texture in textures:
                        if not texture["available"]:
                            add(normalize(name, material.name + ": missing embedded texture " + texture["texture"], names, "ERROR"))
                    if any(texture["name"] not in ("txDiffuse", "txNormal") for texture in textures):
                        add(normalize(name, material.name + ": shader inputs need translation.", names, "REVIEW"))
                    elif data["shader"] not in ("ksPerPixel", "ksPerPixelAT", "ksPerPixelNM"):
                        add(normalize(name, material.name + ": shader family needs a dedicated preview template.", names, "REVIEW"))
                    if data.get("captured_after_import"):
                        add(normalize(name, material.name + ": source was captured after import.", names, "WARNING"))
                    if not textures and data.get("textures") and warnings:
                        add(normalize(name, material.name + ": source inventory is unavailable.", names, "ERROR"))
                yield (index+number/max(1, len(used)))/max(1, len(categories)), "Materials: " + material.name
    return output


def commit(context, root, scope, issues, generation=None, material_generation=None):
    ui_cache.clear_light()
    report = report_for(context, root)
    if report is None:
        report = context.scene.tw_reports.add()
        report.project = root
    report.issues.clear()
    issues = sorted(issues, key=lambda item: ({"ERROR": 0, "WARNING": 1, "REVIEW": 2}[item["severity"]], item["category"], item["message"]))
    for issue in issues:
        item = report.issues.add()
        item.severity, item.category, item.message = issue["severity"], issue["category"], issue["message"]
        item.targets = json.dumps(issue["objects"])
    report.scope = scope
    report.errors = sum(item["severity"] == "ERROR" for item in issues)
    report.warnings = sum(item["severity"] == "WARNING" for item in issues)
    report.reviews = sum(item["severity"] == "REVIEW" for item in issues)
    report.generation = ui_cache._versions["project"] if generation is None else generation
    report.material_generation = ui_cache._versions["material"] if material_generation is None else material_generation
    return report


def filtered_issues(scene, report):
    def build():
        search = scene.tw_issue_search.casefold()
        return [(index, item) for index, item in enumerate(report.issues)
                if scene.tw_issue_filter in ("ALL", item.severity) and search in item.message.casefold()]
    return ui_cache.light(("filtered-issues", scene.tw_issue_filter, scene.tw_issue_search), report, build)


class TW_OT_run_checks(jobs.CooperativeJob, bpy.types.Operator):
    bl_idname = "track_workshop.run_checks"
    bl_label = "Run Checks"
    bl_description = "Run only the requested scope; Cancel retains the previous report"

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and marker_ui.ui_project(context) is not None and not jobs.busy(context)

    def build(self, context):
        context.view_layer.update()
        self.generation = ui_cache._versions["project"]
        self.material_generation = ui_cache._versions["material"]
        self.root = marker_ui.project(context)
        self.scope = context.scene.tw_check_scope
        self.scope_label = {"PROJECT": "Whole Track", "CATEGORY": "Area: " + LABELS[context.scene.tw_check_category],
                            "SELECTED": "Selected Objects: " + LABELS[context.scene.tw_check_category]}[self.scope]
        selected = [obj.name for obj in context.selected_objects if obj.name in self.root.all_objects]
        return collect_steps(context, self.root, self.scope,
                             context.scene.tw_check_category if self.scope != "PROJECT" else "ALL", selected)

    def invoke(self, context, event):
        return self.start(context, self.build(context))

    def execute(self, context):
        try:
            self.completed(context, jobs.drain(self.build(context)))
        except (ValueError, ReferenceError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}

    def completed(self, context, result):
        report = commit(context, self.root, self.scope_label, result, self.generation, self.material_generation)
        self.report({"INFO"}, f"{len(report.issues)} findings")


class TW_OT_focus_issue(bpy.types.Operator):
    bl_idname = "track_workshop.focus_issue"
    bl_label = "Select and Frame"
    bl_description = "Select affected objects and frame them; hidden objects and selection locks are respected"
    bl_options = {"UNDO"}
    index: IntProperty()

    def execute(self, context):
        root = marker_ui.project(context)
        report = report_for(context, root)
        if report is None or not 0 <= self.index < len(report.issues):
            return {"CANCELLED"}
        objects = [root.all_objects.get(name) for name in json.loads(report.issues[self.index].targets)]
        if not objects or any(obj is None or obj.name not in context.view_layer.objects or obj.hide_select
                              or not obj.visible_get(view_layer=context.view_layer) for obj in objects):
            self.report({"WARNING"}, "Affected objects are missing, hidden or locked; visibility was not changed.")
            return {"CANCELLED"}
        for obj in context.selected_objects:
            obj.select_set(False)
        for obj in objects:
            obj.select_set(True)
        context.view_layer.objects.active = objects[0]
        if context.area is not None and context.area.type == "VIEW_3D":
            region = next((region for region in context.area.regions if region.type == "WINDOW"), None)
            if region is not None:
                with context.temp_override(region=region):
                    bpy.ops.view3d.view_selected(use_all_regions=False)
        return {"FINISHED"}


class TW_OT_report_page(bpy.types.Operator):
    bl_idname = "track_workshop.report_page"
    bl_label = "Report Page"
    bl_description = "Browse the filtered findings"
    direction: IntProperty(default=1)

    def execute(self, context):
        scene = context.scene
        report = report_for(context, marker_ui.project(context))
        count = len(filtered_issues(scene, report)) if report else 0
        last = max(0, (count-1)//25)
        scene.tw_issue_page = max(0, min(last, min(last, scene.tw_issue_page)+self.direction))
        return {"FINISHED"}


class TW_PT_checks(bpy.types.Panel):
    bl_label = "Project Checks"
    bl_idname = "TW_PT_checks"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AlterEgo Track Editor"

    @classmethod
    def poll(cls, context):
        return workflow.stage(context, "CHECKS")

    def draw(self, context):
        layout, scene, root = self.layout, context.scene, marker_ui.ui_project(context)
        if root is None:
            layout.label(text="No active track project", icon="INFO")
            return
        layout.prop(scene, "tw_check_scope", text="Scope")
        if scene.tw_check_scope != "PROJECT":
            layout.prop(scene, "tw_check_category", text="Area")
        layout.operator("track_workshop.run_checks", icon="CHECKMARK")
        report = report_for(context, root)
        if report is None:
            layout.label(text="Not checked", icon="INFO")
            return
        if report.generation != ui_cache._versions["project"] or report.material_generation != ui_cache._versions["material"]:
            layout.label(text="Results need refresh", icon="INFO")
        layout.label(text=f"{report.errors+report.warnings+report.reviews} findings")
        for line in textwrap.wrap(report.scope, width=30):
            layout.label(text=line)
        layout.prop(scene, "tw_issue_filter", text="Show")
        layout.prop(scene, "tw_issue_search", text="", icon="VIEWZOOM")
        filtered = filtered_issues(scene, report)
        pages = max(1, (len(filtered)+24)//25)
        page = min(scene.tw_issue_page, pages-1)
        row = layout.row(align=True)
        row.operator("track_workshop.report_page", text="", icon="TRIA_LEFT").direction = -1
        row.label(text=f"{page+1} / {pages}")
        row.operator("track_workshop.report_page", text="", icon="TRIA_RIGHT").direction = 1
        for index, item in filtered[page*25:(page+1)*25]:
            column = layout.column(align=True)
            column.label(text=item.category.title() + " | " + item.severity.title(),
                         icon="ERROR" if item.severity == "ERROR" else "INFO")
            for line in textwrap.wrap(item.message, width=30):
                column.label(text=line)
            if json.loads(item.targets):
                column.operator("track_workshop.focus_issue", text="", icon="VIEWZOOM").index = index


@persistent
def loaded(_):
    for scene in bpy.data.scenes:
        for report in scene.tw_reports:
            report.generation = report.material_generation = -1


def reset_page(scene, context):
    scene.tw_issue_page = 0


CLASSES = (TW_PG_issue, TW_PG_report, TW_OT_run_checks, TW_OT_focus_issue, TW_OT_report_page, TW_PT_checks)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.tw_reports = CollectionProperty(type=TW_PG_report)
    bpy.types.Scene.tw_check_scope = EnumProperty(items=(("PROJECT", "Whole Track", "All project checks"),
        ("CATEGORY", "Area", "Only one area"), ("SELECTED", "Selected Objects", "Findings affecting selected objects")))
    bpy.types.Scene.tw_check_category = EnumProperty(items=CATEGORIES, default="ALL")
    bpy.types.Scene.tw_issue_filter = EnumProperty(items=SEVERITIES, default="ALL", update=reset_page)
    bpy.types.Scene.tw_issue_search = StringProperty(name="Search", update=reset_page)
    bpy.types.Scene.tw_issue_page = IntProperty(default=0, min=0)
    bpy.app.handlers.load_post.append(loaded)


def unregister():
    if loaded in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(loaded)
    for name in ("tw_reports", "tw_check_scope", "tw_check_category", "tw_issue_filter", "tw_issue_search", "tw_issue_page"):
        delattr(bpy.types.Scene, name)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
