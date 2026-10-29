"""Assetto Corsa layout discovery, independent of Blender and AlterEgo."""
import configparser
import json
import math
from pathlib import Path
import re


def layouts(folder):
    if not str(folder).strip():
        raise ValueError("Choose an Assetto Corsa track folder.")
    root = Path(folder).resolve()
    if not root.is_dir():
        raise ValueError("Choose an existing Assetto Corsa track folder.")
    result = []
    for manifest in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        match = re.fullmatch(r"models(?:_(.+))?\.ini", manifest.name, re.IGNORECASE)
        if not manifest.is_file() or not match:
            continue
        identity = match.group(1) or "default"
        candidates = [root / "ui" / identity / "ui_track.json",
                      root / identity / "ui" / "ui_track.json"] if match.group(1) else [root / "ui" / "ui_track.json"]
        name = "Default layout" if identity == "default" else identity.replace("_", " ")
        for metadata in candidates:
            try:
                value = json.loads(metadata.read_text(encoding="utf-8-sig"))
                if isinstance(value, dict) and isinstance(value.get("name"), str) and value["name"].strip():
                    name = value["name"].strip()
                    break
            except (OSError, ValueError):
                pass
        result.append({"id": manifest.name, "name": name, "layout": identity})
    if not result:
        legacy = root / (root.name + ".kn5")
        if not legacy.is_file():
            raise ValueError("No layout files or matching default KN5 found in this track folder.")
        name = root.name
        try:
            metadata = json.loads((root / "ui/ui_track.json").read_text(encoding="utf-8-sig"))
            if isinstance(metadata, dict) and isinstance(metadata.get("name"), str) and metadata["name"].strip():
                name = metadata["name"].strip()
        except (OSError, ValueError):
            pass
        result.append({"id": "@default_kn5", "name": name, "layout": "default"})
    return result


def models(folder, manifest_name):
    root = Path(folder).resolve()
    if manifest_name not in {item["id"] for item in layouts(root)}:
        raise ValueError("Selected layout is no longer available. Choose the track folder again.")
    if manifest_name == "@default_kn5":
        path = (root / (root.name + ".kn5")).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Default KN5 lies outside the track folder.")
        return [{"path": path, "section": "MODEL_0", "position": (0, 0, 0), "rotation": (0, 0, 0)}]
    parser = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";",))
    parser.read_string((root / manifest_name).read_text(encoding="utf-8-sig"))
    result = []
    for section in parser.sections():
        if not re.fullmatch(r"MODEL_\d+", section):
            continue
        row = parser[section]
        path = (root / row.get("FILE", "")).resolve()
        if not path.is_relative_to(root) or path.suffix.lower() != ".kn5" or not path.is_file():
            raise ValueError(f"{section}: missing or unsafe KN5 model: {row.get('FILE', '')}")
        vectors = {}
        for key in ("POSITION", "ROTATION"):
            values = tuple(float(v.strip()) for v in row.get(key, "0,0,0").split(","))
            if len(values) != 3 or not all(math.isfinite(v) for v in values):
                raise ValueError(f"{section}: invalid {key}.")
            vectors[key] = values
        result.append({"path": path, "section": section, "position": vectors["POSITION"],
                       "rotation": vectors["ROTATION"]})
    if not result:
        raise ValueError("The selected layout contains no MODEL entries.")
    return result
