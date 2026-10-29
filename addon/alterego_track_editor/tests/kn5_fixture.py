"""Small static KN5 with one triangle, shared by Blender integration tests."""
import struct


def fixture(path, root_name="root", node_name="triangle", textures=(), properties=(), bindings=(),
            shader="ksPerPixel", blend=0, cutout=0, depth=0):
    def text(value):
        raw = value.encode()
        return struct.pack("<i", len(raw)) + raw
    pack = struct.pack
    raw = b"sc6969" + pack("<ii", 5, len(textures))
    for active, name, payload in textures:
        raw += pack("<i", active) + text(name) + pack("<I", len(payload)) + payload
    raw += pack("<i", 1)
    raw += text("road") + text(shader) + pack("<BBii", blend, cutout, depth, len(properties))
    for name, values in properties:
        raw += text(name) + pack("<10f", *values)
    raw += pack("<i", len(bindings))
    for name, slot, texture in bindings:
        raw += text(name) + pack("<i", slot) + text(texture)
    raw += pack("<i", 1) + text(root_name) + pack("<iB", 1, 1)
    raw += pack("<16f", 1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1)
    raw += pack("<i", 2) + text(node_name) + pack("<iBBBBI", 0, 1, 1, 1, 0, 3)
    for x,y,z,u,v in ((0,0,0,0,0), (1,0,0,1,0), (0,0,1,0,1)):
        raw += pack("<11f", x,y,z, 0,1,0, u,v, 1,0,0)
    raw += pack("<I3HII6fB", 3, 0,1,2, 0,0, 0,1000, 0,0,0,1, 1)
    path.write_bytes(raw)
