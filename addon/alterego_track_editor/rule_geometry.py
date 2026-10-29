"""Arc-length positioning for authoring rules, independent of Blender."""
import math

from . import ai


def at_progress(points, progress):
    segments = ai.lengths(points, False)
    if not math.isfinite(progress) or not 0 <= progress <= 1:
        raise ValueError("Position must be between 0 and 100 percent.")
    distance = sum(segments) * progress
    for index, length in enumerate(segments):
        if distance <= length or index == len(segments)-1:
            t = min(1, max(0, distance / length))
            a, b = points[index:index+2]
            return (tuple(x + (y-x)*t for x, y in zip(a, b)),
                    tuple((y-x)/length for x, y in zip(a, b)))
        distance -= length


def order_issues(values):
    """Entry/exit can coincide with limiter boundaries, not with one another."""
    issues = []
    ordered = ("ENTRY", "LIMITER_START", "LIMITER_END", "EXIT")
    for index, a in enumerate(ordered):
        for b in ordered[index+1:]:
            if a not in values or b not in values:
                continue
            equality_allowed = (a, b) in (("ENTRY", "LIMITER_START"), ("LIMITER_END", "EXIT"))
            if values[a] > values[b] or (values[a] == values[b] and not equality_allowed):
                issues.append((a, b))
    return issues
