"""Static KN5 v5/v6 fields, based on the previously verified format layout."""
import math
import struct
from pathlib import Path


class Reader:
    def __init__(self, stream):
        self.stream = stream
        self.length = stream.seek(0, 2)
        stream.seek(0)
        self.legacy_names = 0

    def take(self, size):
        if size < 0 or size > self.length - self.stream.tell():
            raise ValueError("Truncated KN5 field.")
        return self.stream.read(size)

    def number(self, code):
        return struct.unpack("<" + code, self.take(struct.calcsize("<" + code)))[0]

    def count(self, maximum=1000000):
        value = self.number("i")
        if not 0 <= value <= maximum:
            raise ValueError("Invalid KN5 count.")
        return value

    def text(self):
        raw = self.take(self.count(1048576))
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            # Reversible byte mapping keeps legacy names and texture references identical.
            self.legacy_names += 1
            return raw.decode("latin-1")

    def floats(self, count):
        values = struct.unpack("<" + "f" * count, self.take(count * 4))
        if not all(math.isfinite(v) for v in values):
            raise ValueError("Non-finite KN5 value.")
        return values

    def flag(self):
        value = self.number("B")
        if value not in (0, 1):
            raise ValueError("Invalid KN5 flag.")
        return bool(value)


def read(path):
    images, materials, nodes, texture_records = {}, [], [], []
    with Path(path).open("rb") as stream:
        r = Reader(stream)
        if r.take(6) != b"sc6969":
            raise ValueError("Unsupported or encrypted KN5 file.")
        version = r.number("i")
        if version not in (5, 6):
            raise ValueError("Only static KN5 versions 5 and 6 are supported.")
        header_extra = r.number("i") if version == 6 else None
        for _ in range(r.count(100000)):
            active, name, size = r.number("i"), r.text(), r.number("I")
            if active not in (0, 1):
                raise ValueError(f"Invalid KN5 texture flag {active}: {name}")
            payload = r.take(size)
            if name in images and images[name] != payload:
                raise ValueError(f"Conflicting KN5 texture entries: {name}")
            # Some tracks repeat byte-identical textures within one KN5.
            images[name] = payload
            texture_records.append({"index": len(texture_records), "active": active, "name": name, "size": size})
        for _ in range(r.count(100000)):
            item = {"name": r.text(), "shader": r.text(), "blend": r.number("B"), "cutout": r.flag()}
            item["depth"] = r.number("i")
            item["property_entries"] = [{"name": r.text(), "values": r.floats(10)} for _ in range(r.count(100000))]
            # Keep the legacy lookup as well; the ordered list is authoritative.
            item["properties"] = {entry["name"]: entry["values"] for entry in item["property_entries"]}
            item["textures"] = []
            for _ in range(r.count(100000)):
                name, slot, texture = r.text(), r.number("i"), r.text()
                item["textures"].append({"name": name, "slot": slot, "texture": texture})
            materials.append(item)

        def node(parent, depth):
            if depth > 256 or len(nodes) >= 1000000:
                raise ValueError("Excessive KN5 hierarchy.")
            kind, name, children, active = r.number("i"), r.text(), r.count(), r.flag()
            item = {"kind": kind, "name": name, "parent": parent, "active": active}
            index = len(nodes)
            nodes.append(item)
            if kind == 1:
                item["matrix"] = r.floats(16)
            elif kind == 2:
                item.update(shadows=r.flag(), visible=r.flag(), transparent=r.flag())
                count = r.number("I")
                if count > 65536:
                    raise ValueError("KN5 vertex limit exceeded.")
                item["vertices"] = r.take(count * 44)
                size = r.number("I")
                if size % 3 or size * 2 > r.length - stream.tell():
                    raise ValueError("Invalid KN5 triangles.")
                indices = struct.unpack("<" + "H" * size, r.take(size * 2))
                if indices and max(indices) >= count:
                    raise ValueError("KN5 index outside vertex buffer.")
                item["indices"] = indices
                item.update(material=r.number("I"), layer=r.number("I"), lod=r.floats(2), bounds=r.floats(4), renderable=r.flag())
                if item["material"] >= len(materials):
                    raise ValueError("KN5 material outside table.")
            else:
                raise ValueError("Skinned or unknown KN5 nodes are not supported yet.")
            for _ in range(children):
                node(index, depth + 1)

        node(None, 0)
        if stream.tell() != r.length:
            raise ValueError("Unrecognized trailing KN5 data.")
    warnings = [f"Legacy-encoded names preserved as byte labels: {r.legacy_names}"] if r.legacy_names else []
    return {"images": images, "materials": materials, "nodes": nodes, "warnings": warnings,
            "version": version, "header_extra": header_extra, "texture_records": texture_records}
