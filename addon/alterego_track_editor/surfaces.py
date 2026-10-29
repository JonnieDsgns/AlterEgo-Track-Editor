"""Conservative AC surface suggestions, independent of Blender and rendering."""
import configparser
from pathlib import Path
import re


# Explicit enum numbers keep saved Blender assignments stable across releases.
SURFACES = (
    ("UNASSIGNED", "Unassigned", "No physical surface has been chosen", 0),
    ("ASPHALT", "Asphalt", "Asphalt or tarmac", 1),
    ("KERB", "Kerb", "Kerb or rumble strip", 2),
    ("GRAVEL", "Gravel", "Loose gravel", 3),
    ("GRASS", "Grass", "Natural grass", 4),
    ("CONCRETE", "Concrete", "Concrete surface", 5),
    ("PAVING", "Paving", "Paving stones or cobblestones", 6),
    ("METAL", "Metal", "Metal surface", 7),
    ("OFFTRACK", "Off-track", "Generic off-track surface; not a track-limit rule", 8),
    ("ASTROTURF", "Artificial Grass", "Artificial turf", 9),
)


def load(folder, layout):
    """Read the chosen layout's unpacked definitions; never unpack game data."""
    root = Path(folder).resolve()
    base = root
    if layout != "default":
        base = (root / layout).resolve()
        if not base.is_relative_to(root):
            raise ValueError("Unsafe surface layout path.")
        if not (base / "data").exists() and not (base / "data.acd").exists():
            base = root
    path = base / "data" / "surfaces.ini"
    if not path.resolve().is_relative_to(root):
        raise ValueError("Surface definitions lie outside the track folder.")
    result = {"path": str(path), "definitions": [], "warnings": []}
    if not path.is_file():
        detail = " (packed data.acd is not unpacked)" if (base / "data.acd").is_file() else ""
        result["warnings"].append("No readable surfaces.ini" + detail + "; physical surfaces need review.")
        return result
    parser = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";", "#"))
    try:
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1252")
        parser.read_string(text)
        for section in parser.sections():
            if not re.fullmatch(r"SURFACE_\d+", section, re.IGNORECASE):
                continue
            values = dict(parser[section])
            key = values.get("key", "").strip()
            if not key:
                result["warnings"].append(section + ": missing surface key.")
                continue
            result["definitions"].append({"section": section, "key": key, "values": values})
    except (OSError, UnicodeError, configparser.Error) as error:
        result["definitions"] = []
        result["warnings"].append("Cannot read surfaces.ini: " + str(error))
    return result


def category(key):
    """Qualitative suggestion from explicit surface keys, not visual materials."""
    key = key.upper()
    # Unknown keys are intentionally not inferred from IS_VALID_TRACK or friction.
    aliases = {
        "ROAD": "ASPHALT", "TARMAC": "ASPHALT", "ASPHALT": "ASPHALT",
        "ASPHNEW": "ASPHALT", "RDOLD": "ASPHALT", "PIT": "ASPHALT", "PITS": "ASPHALT",
        "KERB": "KERB", "CURB": "KERB", "GRAVEL": "GRAVEL", "GRASS": "GRASS",
        "CONCRETE": "CONCRETE", "PAVING": "PAVING", "COBBLE": "PAVING",
        "COBBLESTONE": "PAVING", "METAL": "METAL", "OFFTRACK": "OFFTRACK",
        "ASTROTURF": "ASTROTURF", "ASTRO": "ASTROTURF", "TURF": "ASTROTURF",
    }
    if key in aliases:
        return aliases[key]
    # Numbered variants of known keys occur in mod tracks.
    return aliases.get(re.sub(r"[_\d]+$", "", key), "UNASSIGNED")


def suggest(name, definitions):
    physical = re.match(r"^\d+", name)
    result = {"surface": "UNASSIGNED", "collision": bool(physical), "key": "",
              "definition": None, "status": "VISUAL_ONLY", "reason": "No AC physical-mesh prefix."}
    if not physical:
        return result
    suffix = name[physical.end():].upper()
    matches = [row for row in definitions if suffix.startswith(row["key"].upper())]
    result.update(status="NEEDS_REVIEW", reason="No matching AC surface definition.")
    if not matches:
        return result
    longest = max(len(row["key"]) for row in matches)
    matches = [row for row in matches if len(row["key"]) == longest]
    if len(matches) != 1:
        result["reason"] = "Ambiguous AC surface definitions."
        return result
    definition = matches[0]
    surface = category(definition["key"])
    result.update(surface=surface, key=definition["key"], definition=definition,
                  status="SUGGESTED" if surface != "UNASSIGNED" else "NEEDS_REVIEW",
                  reason="Suggestion from AC surface key." if surface != "UNASSIGNED"
                  else "AC surface key has no known surface translation.")
    return result
