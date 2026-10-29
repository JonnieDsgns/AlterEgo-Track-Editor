"""AC marker identities and authoring checks, independent of Blender."""
import math
import re
from collections import Counter, defaultdict


TYPES = (
    ("GRID", "Starting Grid", "Vehicle starting position", 0),
    ("PIT", "Pit Position", "Vehicle position in the pit lane", 1),
    ("TIMING", "Timing Gate", "Left or right endpoint of a timing gate", 2),
    ("HOTLAP", "Hotlap Start", "Separate starting position for a flying lap", 3),
)
SIDES = (("LEFT", "Left", "Left endpoint", 0), ("RIGHT", "Right", "Right endpoint", 1))
LABELS = {row[0]: row[1] for row in TYPES}


def describe(name):
    match = re.fullmatch(r"AC_(START|PIT)_(\d+)", name, re.IGNORECASE)
    if match:
        return {"type": "GRID" if match[1].upper() == "START" else "PIT",
                "number": int(match[2]) + 1, "source_index": int(match[2]), "side": "LEFT"}
    match = re.fullmatch(r"AC_HOTLAP_START_(\d+)", name, re.IGNORECASE)
    if match:
        return {"type": "HOTLAP", "number": int(match[1]) + 1,
                "source_index": int(match[1]), "side": "LEFT"}
    match = re.fullmatch(r"AC_TIME_(\d+)_([LR])", name, re.IGNORECASE)
    if match:
        return {"type": "TIMING", "number": int(match[1]) + 1, "source_index": int(match[1]),
                "side": "LEFT" if match[2].upper() == "L" else "RIGHT"}
    return None


def plan(nodes):
    anchors, displays = {}, {}
    for index, row in enumerate(nodes):
        marker = describe(row["name"])
        if marker is None:
            continue
        parent = row.get("parent")
        ancestor = None
        while parent is not None:
            if describe(nodes[parent]["name"]) == marker:
                ancestor = parent
            parent = nodes[parent].get("parent")
        if ancestor is None:
            anchors[index] = marker
        else:
            displays[index] = ancestor
    return {"anchors": anchors, "displays": displays}


def findings(rows):
    """Warnings, not proof of native timing activation or garage capacity."""
    issues = []

    def add(message, objects=(), severity="ERROR"):
        issues.append({"message": message, "objects": list(objects), "severity": severity})

    counts = Counter(row["type"] for row in rows)
    for kind in ("GRID", "PIT", "TIMING"):
        if not counts[kind]:
            add("Missing " + LABELS[kind].lower() + " markers.")
    seen = Counter()
    members = defaultdict(list)
    pairs = defaultdict(set)
    pair_members = defaultdict(list)
    for row in rows:
        key = (row["type"], row["number"], row["side"] if row["type"] == "TIMING" else "")
        seen[key] += 1
        members[key].append(row["name"])
        if row["type"] == "TIMING":
            pairs[row["number"]].add(row["side"])
            pair_members[row["number"]].append(row["name"])
        position, forward = row.get("position"), row.get("forward")
        if position is not None and not all(math.isfinite(v) for v in position):
            add(row["name"] + ": invalid position.", [row["name"]])
        if forward is not None:
            if not all(math.isfinite(v) for v in forward) or sum(v*v for v in forward) < 1e-12:
                add(row["name"] + ": invalid forward direction.", [row["name"]])
            elif abs(forward[2]) > 0.5 * math.sqrt(sum(v*v for v in forward)):
                add(row["name"] + ": forward direction is steep; check orientation.", [row["name"]], "WARNING")
    for (kind, number, side), count in sorted(seen.items()):
        if count > 1:
            suffix = " " + side.title() if side else ""
            add(f"Duplicate {LABELS[kind].lower()} {number}{suffix} ({count} markers).",
                members[(kind, number, side)])
    for number, sides in sorted(pairs.items()):
        if sides != {"LEFT", "RIGHT"}:
            add(f"Timing gate {number}: missing {'right' if 'LEFT' in sides else 'left'} endpoint.",
                pair_members[number])
    return issues


def validate(rows):
    return [issue["message"] for issue in findings(rows)]
