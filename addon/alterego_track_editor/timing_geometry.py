"""Finite timing-gate crossings and cyclic sector order, independent of Blender."""
import math

from . import ai


def crossing(points, left, right, height_tolerance=3.0):
    segments = ai.lengths(points, True)
    if any(len(p) != 3 or not all(math.isfinite(v) for v in p) for p in (left, right)):
        raise ValueError("Gate contains non-finite positions.")
    s = (right[0]-left[0], right[1]-left[1])
    gate_length = math.hypot(*s)
    if gate_length < 1e-5:
        raise ValueError("Gate endpoints have no horizontal separation.")
    hits, before, total = [], 0.0, sum(segments)

    def cross(a, b):
        return a[0]*b[1]-a[1]*b[0]

    for index, length in enumerate(segments):
        a, b = points[index], points[(index+1) % len(points)]
        r = (b[0]-a[0], b[1]-a[1])
        horizontal = math.hypot(*r)
        q = (left[0]-a[0], left[1]-a[1])
        denominator = cross(r, s)
        if horizontal > 1e-5 and abs(denominator) > 1e-8*horizontal*gate_length:
            t, u = cross(q, s)/denominator, cross(q, r)/denominator
            if -1e-8 <= t <= 1+1e-8 and -1e-8 <= u <= 1+1e-8:
                t, u = min(1, max(0, t)), min(1, max(0, u))
                gap = abs(a[2]+t*(b[2]-a[2]) - (left[2]+u*(right[2]-left[2])))
                if gap <= height_tolerance:
                    progress = ((before+t*length)/total) % 1.0
                    if not any(min(abs(progress-h["progress"]), 1-abs(progress-h["progress"]))*total < 1e-4 for h in hits):
                        hits.append({"progress": progress, "height_gap": gap, "length": total})
        elif horizontal > 1e-5 and abs(cross(q, r))/horizontal < 1e-5:
            # Collinear finite overlap cannot identify a unique timing plane.
            ts = [sum((p[i]-a[i])*r[i] for i in range(2))/(horizontal*horizontal) for p in (left, right)]
            lo, hi = max(0, min(ts)), min(1, max(ts))
            if hi-lo > 1e-8:
                t = (lo+hi)/2
                xy = [a[i]+t*r[i] for i in range(2)]
                u = sum((xy[i]-left[i])*s[i] for i in range(2))/(gate_length*gate_length)
                gap = abs(a[2]+t*(b[2]-a[2]) - (left[2]+u*(right[2]-left[2])))
                if gap <= height_tolerance:
                    raise ValueError("Gate overlaps the Racing Line; choose a transverse gate.")
        before += length
    if len(hits) != 1:
        raise ValueError("Gate does not cross the Racing Line within 3 m height tolerance." if not hits
                         else "Gate crosses the Racing Line more than once.")
    return hits[0]


def sector_order(start, first, second, length):
    distances = ((first-start) % 1.0, (second-start) % 1.0)
    if min(distances[0], distances[1]-distances[0], 1-distances[1])*length < 0.1:
        raise ValueError("Expected Start / Finish, Sector 1, Sector 2 in driving order, at least 0.1 m apart.")
    return distances
