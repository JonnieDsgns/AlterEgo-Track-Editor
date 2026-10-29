"""Persistent static KN5 source contracts, separate from editable Blender nodes."""
import base64
import hashlib
import json
from pathlib import Path
import textwrap

import bpy
from bpy.props import BoolProperty

from . import collection_layout, jobs, kn5, marker_ui, rules, source, ui_cache

SAMPLERS = {"txDiffuse": "Diffuse Color", "txNormal": "Normal Map", "txMaps": "Shader Maps",
            "txDetail": "Detail Color", "txNormalDetail": "Detail Normal", "txMask": "Layer Mask",
            "txDetailR": "Red Layer", "txDetailG": "Green Layer", "txDetailB": "Blue Layer",
            "txDetailA": "Alpha Layer", "txDetailNM": "Layer Normal", "txVariation": "Variation"}


def capture_model(folder, path, data, cache, later=False):
    path = Path(path).resolve()
    relative = path.relative_to(Path(folder).resolve()).as_posix()
    with path.open("rb") as stream:
        file_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    records = []
    payloads = {}
    for record in data["texture_records"]:
        raw = data["images"][record["name"]]
        digest = hashlib.sha256(raw).hexdigest()
        if digest not in cache:
            payload = bpy.data.texts.new("AC Texture " + digest[:16])
            payload.from_string(json.dumps({"encoding": "base64", "sha256": digest,
                                           "data": base64.encodebytes(raw).decode("ascii").splitlines()}, indent=2))
            cache[digest] = payload
        key = "tw_ac_payload_" + str(record["index"])
        payloads[key] = cache[digest]
        records.append(dict(record, sha256=digest, payload_property=key))
    contract = {"schema": 1, "file": relative, "file_sha256": file_hash,
                "kn5_version": data["version"], "header_extra": data["header_extra"],
                "captured_after_import": later, "texture_records": records,
                "materials": data["materials"]}
    model = bpy.data.texts.new("AC Material Source " + Path(relative).name)
    model.from_string(json.dumps(contract, ensure_ascii=True, indent=2))
    for key, value in payloads.items():
        model[key] = value
    model["tw_ac_source_file"] = relative
    return model, contract


def attach(material, index, model, contract, folder):
    ui_cache.invalidate("material")
    identity = hashlib.sha256(json.dumps([Path(folder).name, contract["file"], index]).encode()).hexdigest()
    metadata = dict(contract["materials"][index], schema=1, material_index=index, source_id=identity,
                    file=contract["file"], file_sha256=contract["file_sha256"],
                    captured_after_import=contract["captured_after_import"])
    material["tw_ac_source"] = json.dumps(metadata, ensure_ascii=True)
    material["tw_ac_source_id"] = identity
    material["tw_ac_model_source"] = model
    material["tw_ac_shader"] = metadata["shader"]


def metadata(material):
    try:
        value = json.loads(material.get("tw_ac_source", ""))
        return value if isinstance(value, dict) and value.get("schema") == 1 else None
    except (TypeError, ValueError):
        return None


def active(context):
    obj = context.active_object
    return obj.active_material if obj is not None and obj.type == "MESH" else None


def inventory(material, model_cache=None, *, cached=False):
    data = metadata(material)
    if data is None:
        return None, [], ["Material source has not been captured."]
    model = material.get("tw_ac_model_source")
    try:
        if isinstance(model, bpy.types.Text):
            key = model.as_pointer()
            if model_cache is not None and key in model_cache:
                contract = model_cache[key]
            else:
                contract = (json.loads(model.as_string()) if not cached else
                            ui_cache.resolve("material-contract", model, lambda: json.loads(model.as_string())))
                if model_cache is not None:
                    model_cache[key] = contract
        else:
            contract = None
        if not isinstance(contract, dict) or contract.get("schema") != 1:
            raise ValueError("missing source")
        records = contract["texture_records"]
    except (ValueError, KeyError, TypeError):
        return data, [], ["Material source inventory is missing or invalid."]
    textures, warnings = [], []
    for binding in data["textures"]:
        matches = [record for record in records if record["name"] == binding["texture"]]
        available = bool(matches) and isinstance(model.get(matches[0]["payload_property"]), bpy.types.Text)
        textures.append(dict(binding, available=available))
        if not available:
            warnings.append("Missing embedded texture: " + binding["texture"])
    unsupported = [binding for binding in data["textures"] if binding["name"] not in ("txDiffuse", "txNormal")]
    if unsupported:
        warnings.append(f"{len(unsupported)} additional texture inputs need shader translation.")
    if data["captured_after_import"]:
        warnings.append("Snapshot is from current source files, not verified original import bytes.")
    return data, textures, warnings


def capture_existing(context, root):
    return jobs.drain(capture_existing_steps(context, root))


def capture_existing_steps(context, root):
    from .importer import ImportTransaction
    keys = ("tw_ac_source", "tw_ac_source_id", "tw_ac_model_source", "tw_ac_shader")
    before = {material: {key: material[key] for key in keys if key in material} for material in bpy.data.materials}
    transaction = ImportTransaction()
    iterator = _capture_steps(context, root)
    try:
        while True:
            try:
                update = next(iterator)
            except StopIteration as done:
                return done.value
            transaction.pause()
            yield update
            transaction.resume()
    except BaseException:
        iterator.close()
        ui_cache.invalidate("material")
        for material, values in before.items():
            try:
                for key in keys:
                    if key in values:
                        material[key] = values[key]
                    elif key in material:
                        del material[key]
            except ReferenceError:
                continue
        transaction.rollback()
        raise


def _capture_steps(context, root):
    folder = root.get("tw_track_folder", "")
    entries = source.models(folder, root.get("tw_layout_manifest", ""))
    imported = collection_layout.find(root, "SOURCE")
    if imported is None:
        raise ValueError("Prepare Collections before capturing existing material sources.")
    objects = [obj for obj in imported.all_objects if obj.type == "MESH"]
    files, candidates, conflicts, warnings = {}, {}, set(), []
    for number, entry in enumerate(entries):
        path = str(entry["path"].resolve())
        if path not in files:
            yield 0.2*number/max(1, len(entries)), "Reading " + Path(path).name
            files[path] = kn5.read(path)
    for number, obj in enumerate(objects):
        if number % 250 == 0:
            yield 0.2+0.2*number/max(1, len(objects)), "Matching source materials"
        if len(obj.material_slots) != 1:
            warnings.append(obj.name + ": expected the original single material slot; skipped.")
            continue
        material = obj.active_material
        if material is None or material.get("tw_ac_source") or not material.is_editable:
            continue
        path = str(Path(obj.get("tw_source_model", "")).resolve())
        data = files.get(path)
        index = obj.get("tw_source_node", -1)
        if (data is None or not 0 <= index < len(data["nodes"]) or data["nodes"][index]["kind"] != 2
                or data["nodes"][index]["name"] != obj.get("tw_source_name")):
            warnings.append(obj.name + ": source node no longer matches.")
            continue
        material_index = data["nodes"][index]["material"]
        if material.get("tw_ac_shader") != data["materials"][material_index]["shader"]:
            warnings.append(material.name + ": source shader no longer matches.")
            continue
        target = (path, material_index)
        if material in candidates and candidates[material] != target:
            conflicts.add(material)
        candidates[material] = target
    cache, models = {}, {}
    for number, (material, (path, index)) in enumerate(candidates.items()):
        yield 0.4+0.5*number/max(1, len(candidates)), "Capturing " + material.name
        if material in conflicts:
            warnings.append(material.name + ": shared by different source materials; skipped.")
            continue
        if path not in models:
            models[path] = capture_model(folder, path, files[path], cache, later=True)
        attach(material, index, *models[path], folder)
    # Existing independently copied assets receive the same immutable source references,
    # but no node tree or material slot is replaced.
    by_source = {obj.get("tw_source_id"): obj for obj in objects}
    assets = list(root.all_objects)
    for number, obj in enumerate(assets):
        if number % 250 == 0:
            yield 0.9+0.1*number/max(1, len(assets)), "Linking prepared material sources"
        if obj.type != "MESH" or not obj.get("tw_asset_id") or len(obj.material_slots) != 1:
            continue
        original = by_source.get(obj.get("tw_source_id"))
        old, new = (original.active_material if original else None), obj.active_material
        if (old is not None and new is not None and old.get("tw_ac_source") and not new.get("tw_ac_source")
                and new.is_editable and new.get("tw_ac_shader") == old.get("tw_ac_shader")):
            for key in ("tw_ac_source", "tw_ac_source_id", "tw_ac_model_source"):
                new[key] = old[key]
    return len(candidates)-len(conflicts), warnings


class TW_OT_capture_materials(jobs.CooperativeJob, rules.ProjectOperator, bpy.types.Operator):
    bl_idname = "track_workshop.capture_material_sources"
    bl_label = "Capture Material Sources"
    bl_description = "Read current KN5 files for older projects; retain existing source snapshots and all Blender node edits"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return rules.ProjectOperator.poll(context) and not jobs.busy(context)

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        ui_cache.invalidate("material")
        self.root = marker_ui.project(context)
        iterator = capture_existing_steps(context, self.root)
        if not bpy.app.background:
            return self.start(context, iterator)
        try:
            result = jobs.drain(iterator)
        except (ValueError, OSError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        self.completed(context, result)
        return {"FINISHED"}

    def completed(self, context, result):
        count, warnings = result
        self.report({"WARNING"} if warnings else {"INFO"}, f"Captured {count} material sources; {len(warnings)} warnings")
        self.root["tw_material_capture_warnings"] = "\n".join(warnings)


class TW_PT_materials(bpy.types.Panel):
    bl_label = "AC Materials"
    bl_idname = "TW_PT_materials"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AlterEgo Track Editor"

    @classmethod
    def poll(cls, context):
        from .workflow import stage, own_active
        return stage(context, "MATERIALS") and own_active(context)

    def draw(self, context):
        layout = self.layout
        root = marker_ui.ui_project(context)
        if root is not None:
            layout.operator("track_workshop.capture_material_sources", icon="IMPORT")
            warnings = ui_cache.get("capture-warnings", root,
                lambda: root.get("tw_material_capture_warnings", "").splitlines(), group="material")
            for warning in ui_cache.page(layout, context.scene, warnings, "capture_warnings") if isinstance(warnings, list) else ():
                for index, line in enumerate(textwrap.wrap(warning, width=30)):
                    layout.label(text=line, icon="ERROR" if index == 0 else "NONE")
        material = active(context)
        if material is None:
            layout.label(text="No active mesh material", icon="MATERIAL")
            return
        obj = context.active_object
        if len(obj.material_slots) > 1:
            layout.template_list("MATERIAL_UL_matslots", "", obj.data, "materials", obj, "active_material_index", rows=2)
        layout.label(text=material.name, icon="MATERIAL")
        layout.prop(material, "tw_export_shader", text="F1 Material")
        snapshot = ui_cache.get("material-inventory", material, lambda: inventory(material, cached=True), group="material")
        if not ui_cache.ready(layout, snapshot, group="material"):
            return
        data, textures, warnings = snapshot
        if data is not None:
            layout.label(text="Import Preview: Diffuse / Normal", icon="MATERIAL")
            for value in (data["file"], data["shader"]):
                for line in textwrap.wrap(value, width=30):
                    layout.label(text=line)
            layout.prop(context.scene, "tw_expert")
            if context.scene.tw_expert:
                layout.label(text=f"Source material: {data['material_index']}")
                layout.label(text="Alpha Test: " + ("Yes" if data["cutout"] else "No"))
                layout.label(text=f"Blend (Raw): {data['blend']} | Depth (Raw): {data['depth']}")
                layout.prop(context.scene, "tw_material_parameters", text="Source Parameters")
            if context.scene.tw_expert and context.scene.tw_material_parameters:
                for entry in ui_cache.page(layout, context.scene, data["property_entries"], "parameters"):
                    layout.label(text=entry["name"])
                    for line in textwrap.wrap(", ".join(f"{v:.5g}" for v in entry["values"]), width=30):
                        layout.label(text=line)
            layout.prop(context.scene, "tw_material_textures", text="Texture Bindings")
            if context.scene.tw_material_textures:
                for binding in ui_cache.page(layout, context.scene, textures, "textures"):
                    label = SAMPLERS.get(binding["name"], binding["name"])
                    layout.label(text=f"{label} | Slot {binding['slot']}", icon="IMAGE_DATA" if binding["available"] else "ERROR")
                    for line in textwrap.wrap(binding["texture"], width=30):
                        layout.label(text=line)
        for warning in ui_cache.page(layout, context.scene, warnings, "material_warnings"):
            for index, line in enumerate(textwrap.wrap(warning, width=30)):
                layout.label(text=line, icon="ERROR" if index == 0 else "NONE")


CLASSES = (TW_OT_capture_materials, TW_PT_materials)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.tw_material_parameters = BoolProperty(default=False)
    bpy.types.Scene.tw_material_textures = BoolProperty(default=True)


def unregister():
    del bpy.types.Scene.tw_material_parameters
    del bpy.types.Scene.tw_material_textures
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
