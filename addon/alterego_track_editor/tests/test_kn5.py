import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("workshop_kn5", Path(__file__).parents[1] / "kn5.py")
kn5 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kn5)


def fixture(textures):
    def text(value):
        value = value.encode()
        return struct.pack("<i", len(value)) + value
    pack = struct.pack
    result = b"sc6969" + pack("<ii", 5, len(textures))
    for flag, name, payload in textures:
        result += pack("<i", flag) + text(name) + pack("<I", len(payload)) + payload
    result += pack("<ii", 0, 1) + text("root") + pack("<iB", 0, 1)
    result += pack("<16f", 1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1)
    return result


class TextureTests(unittest.TestCase):
    def read(self, textures):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.kn5"
            path.write_bytes(fixture(textures))
            return kn5.read(path)

    def test_identical_duplicates(self):
        result = self.read([(1,"normal.dds",b"abc"), (1,"normal.dds",b"abc")])
        self.assertEqual(result["images"], {"normal.dds": b"abc"})
        self.assertEqual(len(result["texture_records"]), 2)
        self.assertEqual([record["index"] for record in result["texture_records"]], [0, 1])

    def test_ordered_material_contract(self):
        from kn5_fixture import fixture as material_fixture
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "material.kn5"
            material_fixture(path, textures=[(0, "map.dds", b"raw")],
                             properties=[("same", range(10)), ("same", range(10, 20))],
                             bindings=[("txMaps", 21, "map.dds")], blend=2, cutout=1, depth=7)
            result = kn5.read(path)
            row = result["materials"][0]
            self.assertEqual((row["blend"], row["cutout"], row["depth"]), (2, True, 7))
            self.assertEqual([entry["name"] for entry in row["property_entries"]], ["same", "same"])
            self.assertEqual(list(row["property_entries"][0]["values"]), list(range(10)))
            self.assertEqual(list(row["properties"]["same"]), list(range(10, 20)))
            self.assertEqual(row["textures"][0]["slot"], 21)
            self.assertEqual(result["texture_records"][0]["active"], 0)

    def test_conflicting_duplicates(self):
        with self.assertRaisesRegex(ValueError, "Conflicting.*normal.dds"):
            self.read([(1,"normal.dds",b"abc"), (1,"normal.dds",b"xyz")])

    def test_invalid_flag(self):
        with self.assertRaisesRegex(ValueError, "flag 2"):
            self.read([(2,"normal.dds",b"abc")])

    def test_legacy_texture_name(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.kn5"
            path.write_bytes(fixture([(1,"abc.dds",b"pixels")]).replace(b"abc.dds", b"\xce\xac\xd0.dds"))
            result = kn5.read(path)
            name = next(iter(result["images"]))
            self.assertEqual(name.encode("latin-1"), b"\xce\xac\xd0.dds")
            self.assertTrue(result["warnings"])
