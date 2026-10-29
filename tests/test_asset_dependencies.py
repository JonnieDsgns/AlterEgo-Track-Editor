from pathlib import Path
import struct,tempfile,unittest,json,hashlib
from test_static_asset import add_context
from test_static_family import family_fixture,inputs
from native_fixtures import erp
from alterego_track_editor.asset_dependencies import material_edges,dependency_plan,mip_path
from alterego_track_editor.static_asset import write_asset
from alterego_track_editor.native.storage import Catalog


def material():
    shader=b'eaid://fixture/shared.nefx2\0';labels=b'Color\0Detail\0'
    a=b'eaid://fixture/view_a\0';b=b'eaid://fixture/view_b\0'
    primary=a+b;secondary=b+a;base=104
    offsets=[0,0,len(shader),len(shader)+len(labels),len(shader)+len(labels)+len(primary),len(shader)+len(labels)+len(primary)+len(secondary)]
    head=bytearray(104);struct.pack_into('<I',head,0,2)
    for at,value in zip((8,12,16,20,24,28),offsets):struct.pack_into('<I',head,at,value)
    for i,(usage,kind,name,offset) in enumerate([(1,2,0,0),(2,6,6,len(a))]):
        p=32+36*i
        for at,value in [(0,name),(4,usage),(8,kind),(16,len(a)),(28,offset)]:struct.pack_into('<I',head,p+at,value)
    return bytes(head)+shader+labels+primary+secondary


def fixture(root):
    source=root/'input';source.mkdir();path=source/'source.erp'
    catalog,family=family_fixture(path);catalog,binding=add_context(catalog,path)
    rows=[(name,r.type_name,[catalog.read(name,i) for i in range(len(r.fragments))]) for name,(_,r) in catalog.by_uri.items()]
    for name in ('a','b'):rows.append(('eaid://fixture/'+name+'.material','Material',[material()]))
    native='2025_asset_groups/textures/external.mipmaps';mip=source/native;mip.parent.mkdir(parents=True);mip.write_bytes(bytes(range(256)))
    header=bytearray(36);struct.pack_into('<7I',header,8,15,4,4,0,1,1,0)
    descriptor=bytes([len(native)])+native.encode()+struct.pack('<I',1)+struct.pack('<BQQQ',0,0,256,256)
    for name in ('a','b'):
        surface='eaid://fixture/surface_'+name
        rows.append(('eaid://fixture/view_'+name,'GfxSRVResource',[b'\0'*24+surface.encode()+b'\0']))
        rows.append((surface,'GfxSurfaceRes',[bytes(header),b'\0'*64]+([descriptor] if name=='a' else [])))
    path.write_bytes(erp(rows));catalog=Catalog();catalog.mount(path);catalog.asset_roots=[source]
    return catalog,family,binding,mip


class DependencyTests(unittest.TestCase):
    def test_secondary_and_usage_two_texture_edges(self):
        edges=material_edges(material())
        self.assertEqual(len(edges),5)
        self.assertIn(('Color:secondary','eaid://fixture/view_b'),edges)
        self.assertIn(('Detail:primary','eaid://fixture/view_b'),edges)

    def test_bundle_raw_resources_and_exact_external_mips(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);catalog,family,binding,mip=fixture(root)
            report=write_asset(catalog,family,'eaid://fixture/separate_asset.idf',inputs(),binding,root/'output',True)
            graph=report['dependency_plan'];self.assertEqual(len(graph['nodes']),7)
            self.assertEqual(sum(n['bundled'] for n in graph['nodes']),6)
            self.assertEqual(graph['external_shaders'],['eaid://fixture/shared.nefx2'])
            self.assertFalse(report['dependency_closure_complete'])
            check=Catalog();check.mount(root/'output/asset.erp')
            for name in ('a','b'):
                self.assertEqual(check.read('eaid://fixture/'+name+'.material'),material())
                self.assertEqual(check.read('eaid://fixture/surface_'+name,1),b'\0'*64)
            copied=root/'output'/report['mip_files'][0]['file']
            self.assertEqual(copied.read_bytes(),mip.read_bytes())
            self.assertEqual(report['mip_files'][0]['sha256'],hashlib.sha256(mip.read_bytes()).hexdigest())

    def test_missing_mips_strict_failure_and_no_published_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);catalog,family,binding,mip=fixture(root);mip.unlink()
            with self.assertRaisesRegex(ValueError,'missing or ambiguous'):
                write_asset(catalog,family,'eaid://fixture/separate.idf',inputs(),binding,root/'output',True)
            self.assertFalse((root/'output').exists())
            _,_,report=dependency_plan(catalog,['eaid://fixture/a.material'])
            self.assertTrue(report['errors'])
            for path in ('../bad','C:/bad','/bad','a/.. /bad','a/NUL.txt','a/file:ads','a//b'):
                with self.assertRaises(ValueError):mip_path(path)


if __name__=='__main__':unittest.main()
