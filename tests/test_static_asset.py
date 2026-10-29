from pathlib import Path
import struct,tempfile,unittest,hashlib
from test_static_family import family_fixture,inputs
from native_fixtures import erp
from alterego_track_editor.static_asset import write_asset,relocate_mesh
from alterego_track_editor.native.storage import Catalog
from alterego_track_editor.static_geometry import StaticFamily
from alterego_track_editor.native.geometry import u32


def add_context(catalog,path):
    binding='eaid://fixture/board.emb?context=default';labels=b'Surface\0Fence\0'
    names=[b'eaid://fixture/a.material\0',b'eaid://fixture/b.material\0']
    raw=struct.pack('<3I',2,28,16+len(labels))+struct.pack('<4I',0,0,8,len(names[0]))+labels+b''.join(names)
    rows=[(name,r.type_name,[catalog.read(name,i) for i in range(len(r.fragments))]) for name,(_,r) in catalog.by_uri.items()]
    rows.append((binding,'GfxMatBindRes',[raw]));path.write_bytes(erp(rows));c=Catalog();c.mount(path)
    return c,binding


class StaticAssetTests(unittest.TestCase):
    def test_opaque_extra_records_never_move_for_unequal_names(self):
        with tempfile.TemporaryDirectory() as folder:
            c,family=family_fixture(Path(folder)/'source.erp');uri=family+'?lod=0&mesh'
            raw=bytearray(c.read(uri));struct.pack_into('<II',raw,48,1,len(raw)-76)
            raw.extend(bytes(range(92)))
            t=StaticFamily(c,family).templates[0]
            names={n:'eaid://different/longer_family.idf'+n[len(family):] for n in [*t.vb,t.ib]}
            with self.assertRaisesRegex(ValueError,'equal-length'):relocate_mesh(bytes(raw),names)
            names={n:family.replace('board','other')+n[len(family):] for n in [*t.vb,t.ib]}
            output=relocate_mesh(bytes(raw),names)
            self.assertEqual(len(output),len(raw));self.assertEqual(output[-92:],bytes(range(92)))

    def test_independent_family_relocation_and_dependencies(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'source.erp';c,family=family_fixture(p);c,binding=add_context(c,p)
            before=hashlib.sha256(p.read_bytes()).digest();target='eaid://environment_package/tracks/custom/objects/my_longer_board.idf'
            report=write_asset(c,family,target,inputs(),binding,Path(folder)/'export')
            check=Catalog();check.mount(Path(folder)/'export/asset.erp');rebuilt=StaticFamily(check,target)
            self.assertEqual(len(rebuilt.templates),2)
            self.assertTrue(all(name.startswith(target+'?') or name==report['binding'] for name in check.by_uri))
            self.assertNotIn(family+'?model',check.by_uri)
            self.assertIn((target+'?lod=1&mesh\0').encode(),check.read(target+'?model'))
            self.assertEqual(check.read(report['binding']),c.read(binding))
            self.assertEqual(report['triangles'],[4,4]);self.assertEqual(len(report['material_dependencies']),2)
            self.assertFalse(report['dependency_closure_complete'])
            self.assertEqual(before,hashlib.sha256(p.read_bytes()).digest())
            for template in rebuilt.templates.values():
                self.assertEqual(u32(template.data,76+u32(template.data,60)+16),456)
                self.assertTrue(template.data.endswith(b'OPAQUE MESH TAIL'))
            with self.assertRaises(ValueError):write_asset(c,family,target,inputs(),binding,Path(folder)/'export')
            with self.assertRaises(ValueError):write_asset(c,family,'eaid://bad/../x.idf',inputs(),binding,Path(folder)/'invalid')


if __name__=='__main__':unittest.main()
