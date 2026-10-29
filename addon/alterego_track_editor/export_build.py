"""Small native writer test, direct to DatabaseEditor ZIP, never an authoring archive."""
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import shutil
import time
import uuid

import bpy

from . import export_contract as contract, jobs, marker_ui, materials, rules, ui_cache


def safe_name(name):
    if not name or name in (".", "..") or name.endswith((".", " ")) or any(ord(c) < 32 or c in '/\\:?*"<>|#%' for c in name):
        raise ValueError("Resource name cannot be preserved safely: " + name)
    return name


def image_bytes(image):
    if image is None or image.is_dirty or image.source != "FILE":
        raise ValueError("Save or pack the image before export; generated, dirty and tiled images are not supported yet.")
    if image.packed_file:
        return bytes(image.packed_file.data)
    path = Path(bpy.path.abspath(image.filepath, library=image.library))
    if not path.is_file():
        raise ValueError("Image file is missing: " + image.name)
    return path.read_bytes()


def material_profile(material, payloads=None):
    if material.tw_export_shader == "UNASSIGNED":
        raise ValueError("Choose an F1 material profile.")
    safe_name(material.name)
    data = materials.metadata(material)
    if data and any(item["name"] not in ("txDiffuse", "txNormal") for item in data["textures"]):
        raise ValueError("Additional AC shader inputs need a dedicated translation profile.")
    if not material.use_nodes:
        raise ValueError("Use a Principled BSDF material.")
    output = next((node for node in material.node_tree.nodes if node.type == "OUTPUT_MATERIAL" and node.is_active_output), None)
    links = output.inputs["Surface"].links if output else []
    if len(links) != 1 or links[0].from_node.type != "BSDF_PRINCIPLED":
        raise ValueError("The active output must be connected directly to one Principled BSDF.")
    if any(socket.is_linked for socket in output.inputs if socket.name != "Surface"):
        raise ValueError("Volume and displacement outputs need a dedicated export profile.")
    shader = links[0].from_node
    supported = {"Base Color", "Normal", "Roughness", "Metallic", "Alpha"}
    if any(socket.is_linked and socket.name not in supported for socket in shader.inputs):
        raise ValueError("Additional linked Principled inputs need a dedicated export profile.")
    for name in ("Emission Color", "Emission Strength", "Transmission Weight", "Coat Weight"):
        socket = shader.inputs.get(name)
        if socket and (socket.is_linked or (name != "Emission Color" and name != "Emission Strength" and socket.default_value != 0)):
            raise ValueError(name + " needs a dedicated shader profile.")
    if shader.inputs["Emission Strength"].default_value != 0 and any(shader.inputs["Emission Color"].default_value[:3]):
        raise ValueError("Emission is not supported by the first material profile.")
    channels = {}
    for label, socket_name in (("Color", "Base Color"), ("Normal", "Normal"), ("Roughness", "Roughness"),
                               ("Metallic", "Metallic"), ("Alpha", "Alpha")):
        socket = shader.inputs[socket_name]
        channel = {"Value": list(socket.default_value) if label in ("Color", "Normal") else socket.default_value}
        if label == "Normal":
            channel = {"NormalStrength": 1}
        if socket.is_linked:
            link = socket.links[0]
            node, component = link.from_node, "A" if link.from_socket.name == "Alpha" else "RGB"
            if label == "Normal":
                if node.type != "NORMAL_MAP" or node.space != "TANGENT" or node.uv_map or node.inputs["Strength"].is_linked:
                    raise ValueError("Use an unmodified tangent-space Normal Map node.")
                channel["NormalStrength"] = node.inputs["Strength"].default_value
                if not node.inputs["Color"].is_linked:
                    raise ValueError("Normal Map needs an image input.")
                link = node.inputs["Color"].links[0]
                node, component = link.from_node, "RGB"
            if node.type != "TEX_IMAGE" or node.projection != "FLAT" or node.inputs["Vector"].is_linked:
                raise ValueError(label + ": only a direct UV image is supported by the first profile.")
            if node.extension != "REPEAT" or node.interpolation != "Linear":
                raise ValueError(label + ": use Repeat and Linear image sampling.")
            image = node.image
            raw = image_bytes(image)
            digest = hashlib.sha256(raw).hexdigest()
            name = safe_name(image.name)
            suffix = Path(image.filepath).suffix.lower()
            if suffix not in (".png", ".dds", ".tga", ".bmp", ".jpg", ".jpeg"):
                raise ValueError("Unsupported image encoding: " + name)
            payload = "textures/"+digest+suffix
            if payloads is not None:
                payloads[payload] = raw
            colorspace = image.colorspace_settings.name
            expected = "sRGB" if label == "Color" else "Non-Color"
            if not (label == "Alpha" and component == "A") and colorspace != expected:
                raise ValueError(label + ": image must use " + expected)
            channel["Texture"] = {"Payload": payload, "Sha256": digest, "SourceTexture": name,
                "UVMap": "", "Extension": "REPEAT", "Interpolation": "Linear", "ColorSpace": colorspace,
                "Component": component, "Invert": False}
        channels[label] = channel
    channels["Occlusion"] = {"Value": 1}
    if material.tw_export_shader != "MASK" and (channels["Alpha"].get("Texture") or channels["Alpha"].get("Value") != 1):
        raise ValueError("Transparency requires an explicit Cutout profile; blended transparency is not supported.")
    return {"Version": "AlterEgo.MaterialProfile.v1", "TexturePolicy": "PRESERVE_AUTHORED_TEXTURES",
            "Issues": [], "SourceMaterial": material.name, "AlphaMode": "MASK" if material.tw_export_shader == "MASK" else "OPAQUE",
            "Channels": channels, "shader": material.tw_export_shader}


def native(point):
    return [float(point[0]), float(point[2]), -float(point[1])]


def mesh_snapshot(context, obj, render=True):
    """Deindex by corner to retain UV seams and split normals in both writers."""
    evaluated = obj.evaluated_get(context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        mesh.calc_loop_triangles()
        uv = mesh.uv_layers.active
        if render and uv is None:
            raise ValueError(obj.name + ": UV map missing.")
        if render:
            mesh.calc_tangents(uvmap=uv.name)
        matrix = obj.matrix_world
        normal_matrix = matrix.to_3x3().inverted().transposed()
        reflected = matrix.determinant() < 0
        positions, normals, tangents, texcoords, indices, slots = [], [], [], [], [], []
        for triangle in mesh.loop_triangles:
            loops = list(triangle.loops)
            if reflected:
                loops[1], loops[2] = loops[2], loops[1]
            for loop_index in loops:
                loop = mesh.loops[loop_index]
                normal = (normal_matrix @ mesh.corner_normals[loop_index].vector).normalized()
                tangent = matrix.to_3x3() @ loop.tangent if render else normal.orthogonal()
                tangent = (tangent-normal*tangent.dot(normal)).normalized()
                position = matrix @ mesh.vertices[loop.vertex_index].co
                if not all(math.isfinite(v) for v in (*position, *normal, *tangent)) or tangent.length < .5:
                    raise ValueError(obj.name + ": invalid geometry or tangent frame.")
                positions.append(native(position))
                normals.append(native(normal))
                tangents.append(native(tangent)+[loop.bitangent_sign*(-1 if reflected else 1)])
                texcoords.append(list(uv.data[loop_index].uv) if render else [0, 0])
                indices.append(len(indices))
            slots.append(triangle.material_index)
        if not render:
            return {"positions": positions, "normals": normals, "tangents": tangents, "uv": texcoords,
                    "indices": indices, "slots": [0]*len(slots)}, []
        used = sorted(set(slots))
        remap = {old: new for new, old in enumerate(used)}
        return {"positions": positions, "normals": normals, "tangents": tangents, "uv": texcoords,
                "indices": indices, "slots": [remap[index] for index in slots]}, [mesh.materials[index] for index in used]
    finally:
        evaluated.to_mesh_clear()


def static_glb(context, data, material_count, path):
    """Use Blender's glTF exporter in an isolated temporary scene, not user selection."""
    scene = bpy.data.scenes.new("Track Workshop export staging")
    mesh = bpy.data.meshes.new("Export evaluated mesh")
    obj = bpy.data.objects.new("Export evaluated mesh", mesh)
    temporary_materials = []
    try:
        # Snapshot positions are native Y-up; the glTF exporter performs this conversion itself.
        positions = [(p[0], -p[2], p[1]) for p in data["positions"]]
        mesh.from_pydata(positions, [], [data["indices"][at:at+3] for at in range(0, len(data["indices"]), 3)])
        mesh.update()
        mesh.uv_layers.new(name="UVMap").data.foreach_set("uv", [value for uv in data["uv"] for value in uv])
        mesh.normals_split_custom_set_from_vertices([(n[0], -n[2], n[1]) for n in data["normals"]])
        for index in range(material_count):
            material = bpy.data.materials.new("Export slot " + str(index))
            material["tw_export_slot"] = index
            temporary_materials.append(material)
            mesh.materials.append(material)
        for polygon, slot in zip(mesh.polygons, data["slots"]):
            polygon.material_index, polygon.use_smooth = slot, True
        scene.collection.objects.link(obj)
        with context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
            result = bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_active_scene=True,
                use_selection=False, use_visible=False, export_materials="EXPORT", export_extras=True, export_normals=True,
                export_tangents=True, export_animations=False, export_cameras=False, export_lights=False)
        if result != {"FINISHED"} or not path.is_file():
            raise ValueError("Blender could not export evaluated static geometry.")
    finally:
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.scenes.remove(scene)
        bpy.data.meshes.remove(mesh)
        for material in temporary_materials:
            bpy.data.materials.remove(material)


def backend_path(context):
    addon = context.preferences.addons.get(__package__)
    override = addon.preferences.backend if addon else ""
    if override:
        return Path(bpy.path.abspath(override)).resolve()
    bundled = Path(__file__).parent/"backend/TrackWorkshop.Native.dll"
    development = Path(__file__).parent.parent/"TrackWorkshopBackend/bin/Debug/net9.0/TrackWorkshop.Native.dll"
    return bundled if bundled.is_file() or not development.is_file() else development


def build_steps(context, root):
    from . import export_ui
    yield 0, "Checking export inputs"
    context.view_layer.update()
    initial = tuple(ui_cache._versions.values())
    plan = yield from export_ui.plan_steps(context, root)
    if initial != tuple(ui_cache._versions.values()):
        raise ValueError("Scene changed during export planning; start the native test again.")
    if not plan["geometry_test_ready"]:
        raise ValueError("Resolve geometry export blockers in Check Export first.")
    backend = backend_path(context)
    if not backend.is_file():
        raise ValueError("Native backend missing. Set Native Backend in add-on preferences.")
    base = contract.require_output(plan["settings"]["output"], plan["settings"]["game_root"])
    folder = base/(plan["settings"]["build_name"]+"_"+uuid.uuid4().hex[:12])
    folder.mkdir(parents=True, exist_ok=False)
    process = None
    status = {"stage": "BUILDING", "game_verified": False, "track_export_ready": False}
    try:
        (folder/"export-plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
        payloads, profiles, objects = {}, {}, []
        for number, row in enumerate(plan["objects"]):
            context.view_layer.update()
            checkpoint = tuple(ui_cache._versions.values())
            yield .1+.4*number/max(1, len(plan["objects"])), "Capturing " + row["name"]
            if checkpoint != tuple(ui_cache._versions.values()):
                raise ValueError("Scene changed during export capture; start the native test again.")
            obj = root.all_objects.get(row["name"])
            if obj is None:
                raise ValueError("An export object was removed; run Check Export again.")
            data, slots = mesh_snapshot(context, obj, render=row["render_role"] != "PHYSICS")
            keys = []
            for material in slots:
                if material is None:
                    raise ValueError(obj.name + ": empty material slots are not supported by the native test.")
                key = hashlib.sha256(material.name.encode()).hexdigest()[:24]
                profiles[key] = material_profile(material, payloads)
                keys.append(key)
            entry = dict(row, geometry=data, materials=keys)
            if row["render_role"] == "STATIC":
                glb = folder/("object_"+str(number)+".glb")
                static_glb(context, data, len(slots), glb)
                entry["glb"] = str(glb)
            objects.append(entry)
        for path, raw in payloads.items():
            target = folder/path
            if os.name == "nt" and not str(target).startswith("\\\\?\\"):
                target = Path("\\\\?\\"+str(target))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        job = {"version": contract.JOB_VERSION, "settings": plan["settings"], "policy": contract.DONOR_POLICY,
               "objects": objects, "materials": profiles, "output": str(folder), "mode": "STRUCTURAL_TEST"}
        job_path = folder/"native-job.json"
        job_path.write_text(json.dumps(job, allow_nan=False), encoding="utf-8")
        with (folder/"backend.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen(["dotnet", str(backend), str(job_path)], stdout=log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            while process.poll() is None:
                if bpy.app.background:
                    time.sleep(.03)
                yield .65, "Writing and checking native resources", True
            if process.returncode != 0:
                raise ValueError("Native build failed; see " + str(folder/"backend.log"))
        result = json.loads((folder/"result.json").read_text(encoding="utf-8"))
        if result.get("stage") != "STRUCTURAL_TEST_PASSED" or result.get("game_verified") is not False:
            raise ValueError("Native backend returned an invalid result.")
        status = result
        return result
    except BaseException as error:
        status = {"stage": "CANCELLED" if isinstance(error, GeneratorExit) else "FAILED", "error": str(error),
                  "game_verified": False, "track_export_ready": False}
        raise
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait()
        if status["stage"] in ("CANCELLED", "FAILED"):
            (folder/"native-test.zip").unlink(missing_ok=True)
        (folder/"build-status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")


class TW_OT_native_test(jobs.CooperativeJob, rules.ProjectOperator, bpy.types.Operator):
    bl_idname = "track_workshop.native_test"
    bl_label = "Build Native Test ZIP"
    bl_description = "Build a small structural DatabaseEditor test, not a playable or installation-verified track"

    @classmethod
    def poll(cls, context):
        return rules.ProjectOperator.poll(context) and not jobs.busy(context)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        self.layout.label(text="Structural test only", icon="ERROR")
        self.layout.label(text="Not a playable track. Do not install in the game.")

    def execute(self, context):
        self.report({"ERROR"}, "Native export is not included in this foundation build")
        return {"CANCELLED"}
    def completed(self, context, result):
        self.root.tw_export.last_build = result["package"]
        self.report({"WARNING"}, "Native test ZIP written. Not a playable track; no game files changed.")


class TW_OT_new_export_test(bpy.types.Operator):
    bl_idname = "track_workshop.new_export_test"
    bl_label = "New Export Test Scene"
    bl_description = "Create a separate small project for native writer testing; existing track data is retained"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and not jobs.busy(context)

    def execute(self, context):
        from . import collection_layout
        previous = marker_ui.project(context)
        root = bpy.data.collections.new("Native Export Test")
        root["tw_project_id"] = str(uuid.uuid4())
        context.scene.collection.children.link(root)
        groups = collection_layout.ensure(root)
        if previous is not None:
            root.tw_export.game_root = previous.tw_export.game_root
            root.tw_export.output = previous.tw_export.output
            root.tw_export.author = previous.tw_export.author
        root.tw_export.track_name = "Native Writer Test"
        first = None
        for name, role, positions, faces, shader, surface in (
                ("Test Terrain", "COMMON_TERRAIN", [(0,0,0),(20,0,0),(20,20,0),(0,20,0)], [(0,1,2),(0,2,3)], "TERRAIN", "ASPHALT"),
                ("Test Object", "COMMON_OBJECTS", [(8,5,0),(10,5,0),(8,7,2)], [(0,1,2)], "OPAQUE", "CONCRETE")):
            mesh = bpy.data.meshes.new(name)
            mesh.from_pydata(positions, [], faces)
            mesh.update()
            mesh.uv_layers.new(name="UVMap")
            for loop in mesh.loops:
                point = positions[loop.vertex_index]
                mesh.uv_layers.active.data[loop.index].uv = point[:2]
            obj = bpy.data.objects.new(name, mesh)
            groups[role].objects.link(obj)
            obj["tw_project_id"], obj["tw_asset_id"] = root["tw_project_id"], str(uuid.uuid4())
            obj.tw_surface.collision, obj.tw_surface.surface = True, surface
            material = bpy.data.materials.new(name + " Material")
            material.use_nodes = True
            material.tw_export_shader = shader
            mesh.materials.append(material)
            first = first or obj
        for obj in context.selected_objects:
            obj.select_set(False)
        first.select_set(True)
        context.view_layer.objects.active = first
        context.scene.tw_marker_project = root
        context.scene.tw_project_pinned = True
        context.scene.tw_workflow_stage = "EXPORT"
        ui_cache.invalidate()
        return {"FINISHED"}


CLASSES = (TW_OT_native_test, TW_OT_new_export_test)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
