"""Explicit export profile and cancellable, read-only DatabaseEditor preflight."""
import json
import math
import shutil
import textwrap

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, IntProperty, PointerProperty, StringProperty

from . import export_contract as contract, jobs, marker_ui, materials, routes, rules, timing, ui_cache, workflow

MATERIAL_MODES = (("UNASSIGNED", "Unassigned", "Choose the native material contract"),
                  ("TERRAIN", "Terrain", "Single-layer native terrain"),
                  ("OPAQUE", "Opaque Object", "Opaque static model"),
                  ("MASK", "Cutout Object", "Alpha-tested static model, not blended transparency"))


def export_changed(self, context):
    ui_cache.invalidate("export")


class TW_PG_export_issue(bpy.types.PropertyGroup):
    message: StringProperty()
    severity: StringProperty()
    targets: StringProperty()
    scope: StringProperty()


class TW_PG_export(bpy.types.PropertyGroup):
    slot: EnumProperty(name="Replace Track", items=(("imola", "Imola", "First verified backend target"),), update=export_changed)
    variant: EnumProperty(name="Variant", items=(("2025_F1", "F1 2025", "Common plus F1 2025 assets"),), update=export_changed)
    game_root: StringProperty(name="F1 25 Folder", subtype="DIR_PATH",
        default="", update=export_changed)
    output: StringProperty(name="Output Folder", subtype="DIR_PATH", update=export_changed)
    track_name: StringProperty(name="Track Name", default="Custom Track", update=export_changed)
    author: StringProperty(name="Author", default="", update=export_changed)
    build_name: StringProperty(name="Build Name", default="track_test", update=export_changed)
    details: BoolProperty(name="Donor Policy")
    report: StringProperty(options={"HIDDEN"})
    generation: IntProperty(default=-1)
    material_generation: IntProperty(default=-1)
    export_generation: IntProperty(default=-1)
    ready: BoolProperty(default=False)
    mesh_count: IntProperty()
    triangle_count: IntProperty()
    page: IntProperty(default=0, min=0)
    issues: CollectionProperty(type=TW_PG_export_issue)
    last_build: StringProperty()


def settings(root):
    profile = root.tw_export
    values = {name: getattr(profile, name) for name in ("slot", "variant", "game_root", "output", "track_name", "author", "build_name")}
    for name in ("game_root", "output"):
        if values[name]:
            values[name] = bpy.path.abspath(values[name])
    return values


def stale(root):
    profile = root.tw_export
    return (not profile.report or profile.generation != ui_cache._versions["project"]
            or profile.material_generation != ui_cache._versions["material"] or profile.export_generation != ui_cache._versions["export"])


def candidates(root):
    """Resolve actual project-owned collection membership, never visibility or names."""
    owned = {root, *root.children_recursive}
    tagged = {collection: collection.get("tw_collection_role") for collection in owned
              if collection.get("tw_collection_owner") == root.get("tw_project_id")}
    selected = {}
    excluded = {"SOURCE", "MARKUP"}

    def walk(collection, ancestors):
        role = tagged.get(collection)
        path = ancestors + ([role] if role else [])
        for obj in collection.objects:
            selected.setdefault(obj, []).append(tuple(path))
        for child in collection.children:
            walk(child, path)
    walk(root, [])
    output, skipped, issues = [], [], []
    for obj, paths in selected.items():
        valid = [path for path in paths if not excluded.intersection(path)
                 and ("COMMON" in path or "2025_F1" in path)]
        if not valid or any(obj.get(flag) for flag in (*ui_cache.AUTHORING_FLAGS, "tw_marker_helper", "tw_marker_source_only")):
            skipped.append(obj.name)
            continue
        if obj.type != "MESH":
            if obj.type != "EMPTY" or obj.instance_type != "NONE":
                issues.append(contract.issue("OBJECT_TYPE", obj.name + ": convert non-mesh geometry and instances before the native test.", [obj.name]))
            skipped.append(obj.name)
            continue
        if obj.get("tw_project_id") not in (None, root.get("tw_project_id")):
            issues.append(contract.issue("FOREIGN_PROJECT", obj.name + ": mesh belongs to another track project.", [obj.name]))
        roles = {"TERRAIN" if "COMMON_TERRAIN" in path else "STATIC" for path in valid}
        if len(roles) != 1 or any("SOURCE" in path for path in paths):
            issues.append(contract.issue("AMBIGUOUS_MEMBERSHIP", obj.name + ": conflicting source/terrain/object memberships.", [obj.name]))
        if obj.hide_render and not obj.tw_surface.collision:
            skipped.append(obj.name)
            continue
        output.append((obj, "PHYSICS" if obj.hide_render else "TERRAIN" if "TERRAIN" in roles else "STATIC"))
    return output, skipped, issues


def plan_steps(context, root):
    from .export_build import material_profile, backend_path
    current = settings(root)
    output, skipped, issues = candidates(root)
    issues = contract.validate_settings(current)+issues
    if not backend_path(context).is_file():
        issues.append(contract.issue("BACKEND", "Native backend is missing; choose TrackWorkshop.Native.dll in add-on preferences."))
    if not shutil.which("dotnet"):
        issues.append(contract.issue("DOTNET", "Install the .NET 9 runtime to run the native backend."))
    rows, material_cache, identities = [], {}, set()
    depsgraph = context.evaluated_depsgraph_get()
    for number, (obj, role) in enumerate(output):
        yield number/max(1, len(output)), "Export plan: " + obj.name
        triangles = 0
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            mesh.calc_loop_triangles()
            triangles = len(mesh.loop_triangles)
            if role != "PHYSICS" and not mesh.uv_layers.active:
                issues.append(contract.issue("UV_MISSING", obj.name + ": add an active UV map.", [obj.name]))
            if not triangles:
                issues.append(contract.issue("EMPTY_MESH", obj.name + ": no triangles.", [obj.name]))
            if any(not math.isfinite(value) for row in obj.matrix_world for value in row) or abs(obj.matrix_world.determinant()) < 1e-12:
                issues.append(contract.issue("TRANSFORM", obj.name + ": invalid or singular world transform.", [obj.name]))
            if role == "STATIC" and triangles > contract.MAX_OBJECT_TRIANGLES:
                issues.append(contract.issue("OBJECT_BUDGET", obj.name + ": split this mesh below 20,000 triangles for the native test.", [obj.name]))
            used = {triangle.material_index for triangle in mesh.loop_triangles} if role != "PHYSICS" else set()
            for index in used:
                material = mesh.materials[index] if index < len(mesh.materials) else None
                if material is None:
                    issues.append(contract.issue("MATERIAL_MISSING", obj.name + ": an evaluated triangle has no material.", [obj.name]))
                    continue
                if material not in material_cache:
                    try:
                        material_profile(material)
                        material_cache[material] = None
                    except (ValueError, OSError, RuntimeError) as error:
                        material_cache[material] = str(error)
                if material_cache[material]:
                    issues.append(contract.issue("MATERIAL", obj.name + " / " + material.name + ": " + material_cache[material], [obj.name]))
                expected = "TERRAIN" if role == "TERRAIN" else ("OPAQUE", "MASK")
                if material.tw_export_shader not in ((expected,) if isinstance(expected, str) else expected):
                    issues.append(contract.issue("SHADER_ROLE", obj.name + " / " + material.name + ": material profile does not match its export collection.", [obj.name]))
        finally:
            evaluated.to_mesh_clear()
        collision = obj.tw_surface.collision
        surface = obj.tw_surface.surface
        if collision and surface not in contract.SURFACE_CODES:
            issues.append(contract.issue("SURFACE", obj.name + ": assign a physical surface.", [obj.name]))
        if obj.instance_type != "NONE":
            issues.append(contract.issue("INSTANCES", obj.name + ": instance expansion is not supported by the native test.", [obj.name]))
        identity = obj.get("tw_asset_id") or obj.get("tw_source_id") or obj.name
        if identity in identities:
            issues.append(contract.issue("DUPLICATE_ID", obj.name + ": duplicate export object identity.", [obj.name]))
        identities.add(identity)
        rows.append({"name": obj.name, "id": identity,
                     "render_role": role, "triangles": triangles, "collision": collision,
                     "surface": surface, "physics_code": contract.SURFACE_CODES.get(surface),
                     "materials": [material.name if material else None for material in obj.data.materials]})
    for category, findings in (("LINES", lambda: routes.findings(root)), ("RULES", lambda: rules.findings(root)),
                               ("TIMING", lambda: timing.state(root)[1])):
        yield .95, "Export plan: " + category.title()
        for finding in findings():
            issues.append(contract.issue(category, finding["message"], severity=finding.get("severity", "WARNING"), scope="TRACK"))
    return contract.finish(current, rows, issues, skipped)


def save_plan(root, result, generations):
    profile = root.tw_export
    profile.report = json.dumps(result, indent=2, ensure_ascii=True)
    profile.issues.clear()
    for row in result["issues"]:
        item = profile.issues.add()
        item.message, item.severity, item.scope = row["message"], row["severity"], row["scope"]
        item.targets = json.dumps(row["objects"])
    profile.ready = result["geometry_test_ready"]
    profile.mesh_count, profile.triangle_count = len(result["objects"]), result["triangles"]
    profile.generation, profile.material_generation, profile.export_generation = generations
    profile.page = 0


class TW_OT_export_plan(jobs.CooperativeJob, rules.ProjectOperator, bpy.types.Operator):
    bl_idname = "track_workshop.export_plan"
    bl_label = "Check Export"
    bl_description = "Create a DatabaseEditor export plan without generating game resources"

    @classmethod
    def poll(cls, context):
        return rules.ProjectOperator.poll(context) and not jobs.busy(context)

    def execute(self, context):
        context.view_layer.update()
        self.root = marker_ui.project(context)
        self.generations = tuple(ui_cache._versions[name] for name in ("project", "material", "export"))
        iterator = plan_steps(context, self.root)
        if not bpy.app.background:
            return self.start(context, iterator)
        self.completed(context, jobs.drain(iterator))
        return {"FINISHED"}

    def completed(self, context, result):
        save_plan(self.root, result, self.generations)
        self.report({"INFO"}, f"Export plan: {len(result['objects'])} meshes; {len(result['issues'])} findings")


class TW_OT_export_issue(bpy.types.Operator):
    bl_idname = "track_workshop.export_issue"
    bl_label = "Select Export Finding"
    index: IntProperty()

    def execute(self, context):
        root = marker_ui.project(context)
        if root is None or not 0 <= self.index < len(root.tw_export.issues):
            return {"CANCELLED"}
        names = json.loads(root.tw_export.issues[self.index].targets)
        objects = [root.all_objects.get(name) for name in names]
        if not objects or any(obj is None or obj.hide_select or not obj.visible_get() for obj in objects):
            self.report({"WARNING"}, "Affected objects are missing, hidden or locked.")
            return {"CANCELLED"}
        for obj in context.selected_objects:
            obj.select_set(False)
        for obj in objects:
            obj.select_set(True)
        context.view_layer.objects.active = objects[0]
        return {"FINISHED"}


class TW_PT_database_export(bpy.types.Panel):
    bl_label = "DatabaseEditor Export"
    bl_idname = "TW_PT_database_export"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AlterEgo Track Editor"

    @classmethod
    def poll(cls, context):
        return workflow.stage(context, "EXPORT")

    def draw(self, context):
        layout, root = self.layout, marker_ui.ui_project(context)
        layout.operator("track_workshop.new_export_test", icon="MESH_GRID")
        if root is None:
            layout.label(text="No active track project", icon="INFO")
            return
        profile = root.tw_export
        for name in ("slot", "variant", "game_root", "output", "track_name", "author", "build_name"):
            layout.prop(profile, name)
        layout.prop(profile, "details")
        if profile.details:
            for value in ("Own geometry and collision", "Own routes and marker positions", "Imola: native / shader templates", "Imola: environment baseline", "Imola: vehicle baseline", "No original Imola road geometry"):
                for line in textwrap.wrap(value, width=30):
                    layout.label(text=line)
        material = materials.active(context) if workflow.own_active(context) else None
        if material is not None:
            for line in textwrap.wrap(material.name, width=30):
                layout.label(text=line, icon="MATERIAL")
            layout.prop(material, "tw_export_shader", text="Material")
        layout.operator("track_workshop.export_plan", icon="CHECKMARK")
        layout.operator("track_workshop.native_test", icon="EXPORT")
        if profile.report:
            layout.label(text="Plan needs refresh" if stale(root) else "Plan checked", icon="INFO")
            layout.label(text=f"{profile.mesh_count} meshes | {profile.triangle_count} triangles")
            layout.label(text="Full track build: pending", icon="INFO")
            count = len(profile.issues)
            pages = max(1, (count+9)//10)
            if pages > 1:
                layout.prop(profile, "page", text="Findings Page")
            page = min(profile.page, pages-1)
            for index in range(page*10, min(count, (page+1)*10)):
                item = profile.issues[index]
                for line in textwrap.wrap(item.message, width=30):
                    layout.label(text=line, icon="ERROR" if item.severity == "ERROR" else "INFO")
                if item.targets != "[]":
                    layout.operator("track_workshop.export_issue", text="", icon="RESTRICT_SELECT_OFF").index = index
        if profile.last_build:
            for line in textwrap.wrap(profile.last_build, width=30):
                layout.label(text=line)


CLASSES = (TW_PG_export_issue, TW_PG_export, TW_OT_export_plan, TW_OT_export_issue, TW_PT_database_export)


@persistent
def loaded(_):
    for collection in bpy.data.collections:
        if collection.tw_export.report:
            collection.tw_export.generation = collection.tw_export.export_generation = -1


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Collection.tw_export = PointerProperty(type=TW_PG_export)
    bpy.types.Material.tw_export_shader = EnumProperty(name="F1 Material", items=MATERIAL_MODES, default="UNASSIGNED", update=export_changed)
    bpy.app.handlers.load_post.append(loaded)


def unregister():
    if loaded in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(loaded)
    del bpy.types.Material.tw_export_shader
    del bpy.types.Collection.tw_export
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
