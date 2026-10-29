"""Synthetic AC v7 AI bytes with optional detail/grid blocks."""
import struct


def payload(points, widths=None, grid=False):
    pack = struct.pack
    raw = pack("<4i", 7, len(points), 90000, 1)
    for index, point in enumerate(points):
        raw += pack("<4fi", *point, index*10.0, index)
    raw += pack("<i", len(points) if widths is not None else 0)
    if widths is not None:
        for l, r in widths:
            raw += pack("<18f", 30, 0.5, 0, 0, 0, l, r, 0, 1, 0, 1, 0, 10, 1, 0, 0, 0, 0)
    raw += pack("<i", int(grid))
    if grid:
        raw += pack("<6fifi", 0, 0, 0, 100, 1, 100, 1, 2, 1)
        raw += pack("<4i", 1, 2, 0, 1)
    return raw
