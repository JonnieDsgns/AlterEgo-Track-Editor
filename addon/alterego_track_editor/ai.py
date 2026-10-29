"""Verified AC v7 AI layout and small route-authoring geometry helpers."""
import math
import io
from pathlib import Path

from .kn5 import Reader

FIELDS = ("speed", "gas", "brake", "obsolete_lat_g", "radius", "side_left", "side_right", "camber",
          "direction", "normal_x", "normal_y", "normal_z", "length", "forward_x", "forward_y", "forward_z",
          "tag", "grade")


def read(path):
    return parse(Path(path).read_bytes())


def parse(payload):
    with io.BytesIO(payload) as stream:
        r = Reader(stream)
        if r.number("i") != 7:
            raise ValueError("Only AC AI version 7 is supported.")
        count, lap_time, samples = r.count(100000), r.number("i"), r.number("i")
        if count < 2 or count * 20 > r.length - stream.tell():
            raise ValueError("Invalid AC AI point count.")
        points = []
        for _ in range(count):
            values, identity = r.floats(4), r.number("i")
            if values[3] < 0:
                raise ValueError("Negative AC AI distance.")
            points.append({"position": list(values[:3]), "distance": values[3], "id": identity})
        extra = r.count(100000)
        if extra not in (0, count) or extra * 72 > r.length - stream.tell():
            raise ValueError("AC AI detail count does not match the route.")
        for index in range(extra):
            points[index]["hints"] = dict(zip(FIELDS, r.floats(18)))
        grid = r.number("i")
        if grid not in (0, 1):
            raise ValueError("Invalid AC AI grid flag.")
        if grid:
            r.floats(6)
            r.number("i")
            r.floats(1)
            for _ in range(r.count()):
                for _ in range(r.count()):
                    r.take(r.count() * 4)
        if stream.tell() != r.length:
            raise ValueError("Unrecognized trailing AC AI data.")
    return {"version": 7, "lap_time": lap_time, "samples": samples, "points": points, "has_grid": bool(grid)}


def files(folder, layout):
    root = Path(folder).resolve()
    base = root if layout == "default" else (root / layout).resolve()
    if not base.is_relative_to(root):
        raise ValueError("Unsafe AC AI layout path.")
    # Never borrow another layout's AI. A named layout must have its own files.
    result = []
    for filename, kind in (("fast_lane.ai", "RACING_LINE"), ("pit_lane.ai", "PIT_LINE")):
        path = (base / "ai" / filename).resolve()
        if not path.is_relative_to(root):
            raise ValueError("AC AI file lies outside the track folder.")
        result.append((kind, path))
    return result


def blender_position(point):
    return (point[0], -point[2], point[1])


def lengths(points, closed):
    if len(points) < (3 if closed else 2):
        raise ValueError("The line has too few points.")
    if any(len(p) != 3 or not all(math.isfinite(v) for v in p) for p in points):
        raise ValueError("The line contains non-finite positions.")
    pairs = list(zip(points, points[1:] + points[:1])) if closed else list(zip(points, points[1:]))
    values = [math.dist(a, b) for a, b in pairs]
    if any(value < 1e-5 for value in values):
        raise ValueError("The line contains coincident neighbouring points.")
    return values


def boundaries(points, widths, normals, closed):
    lengths(points, closed)
    if len(widths) != len(points) or len(normals) != len(points):
        raise ValueError("Point count changed. Set widths for all points before updating road edges.")
    left, right = [], []
    for index, point in enumerate(points):
        a = points[(index - 1) % len(points)] if closed or index else point
        b = points[(index + 1) % len(points)] if closed or index < len(points) - 1 else point
        tangent = [y-x for x, y in zip(a, b)]
        normal = normals[index]
        if not all(math.isfinite(v) for v in normal) or sum(v*v for v in normal) < 1e-8:
            normal = (0, 0, 1)
        nx, ny, nz = normal
        tx, ty, tz = tangent
        side = (ny*tz-nz*ty, nz*tx-nx*tz, nx*ty-ny*tx)
        size = math.sqrt(sum(v*v for v in side))
        if size < 1e-6:
            raise ValueError(f"Point {index+1}: ambiguous tangent or surface normal.")
        l, r = widths[index]
        if not all(math.isfinite(v) and 0 < v <= 1000 for v in (l, r)):
            raise ValueError(f"Point {index+1}: set positive left/right widths.")
        left.append(tuple(p + s*l/size for p, s in zip(point, side)))
        right.append(tuple(p - s*r/size for p, s in zip(point, side)))
    return left, right


def nearest(points, point, closed=True):
    segments = lengths(points, closed)
    total, before, best = sum(segments), 0.0, None
    for index, length in enumerate(segments):
        a, b = points[index], points[(index+1) % len(points)]
        vector = [y-x for x, y in zip(a, b)]
        t = max(0.0, min(1.0, sum((p-x)*v for p, x, v in zip(point, a, vector)) / (length*length)))
        projected = [x+t*v for x, v in zip(a, vector)]
        distance = math.dist(point, projected)
        if best is None or distance < best["distance"]:
            best = {"position": projected, "distance": distance, "progress": (before+t*length)/total,
                    "segment": index, "fraction": t}
        before += length
    return best
