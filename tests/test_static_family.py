from pathlib import Path
import hashlib
import struct
import tempfile
import unittest
from test_static_geometry import static_fixture,authored
from native_fixtures import erp
from alterego_track_editor.static_geometry import StaticFamily,StaticTemplate,write_family_test
from alterego_track_editor.native.storage import Catalog
from alterego_track_editor.native.geometry import mesh,u32


def family_fixture(path):
    """Two material submeshes, two LODs, shared attribute and index streams."""
    catalog,uri=static_fixture(path);family=uri.split('?')[0]
    original=catalog.read(uri);data=bytearray(original[:164]+original[76:164]+original[164:])
    struct.pack_into('<I',data,0,2)
    for p in (20,24,28,32,40,44,60):struct.pack_into('<I',data,p,u32(original,p)+88)
    # Add another native material name; move declaration/binding/draw regions.
    end=76+u32(data,32);data[end:end]=b'Fence\0'
    for p in (32,40,44,60):struct.pack_into('<I',data,p,u32(data,p)+6)
    struct.pack_into('<I',data,76+88+48,len(b'Surface\0'))
    struct.pack_into('<3I',data,76+88+12,3,3,0)
    draw=76+u32(data,60);data[draw+16:draw+16]=struct.pack('<4I',456,1,3,3)
    struct.pack_into('<I',data,56,2)
    resources=[]
    for name,(_,resource) in catalog.by_uri.items():
        fragments=[catalog.read(name,i) for i in range(len(resource.fragments))]
        if name==uri:
            fragments=[bytes(data)]
            resources.append((family+'?lod=1&mesh',resource.type_name,fragments))
        elif name==family+'?model':
            model=bytearray(fragments[0]);struct.pack_into('<I',model,0,2);struct.pack_into('<I',model,12,2)
            model[72:72]=b'\0'*8;fragments=[bytes(model)]
        elif name==family+'?ib=0':
            header=bytearray(fragments[0]);struct.pack_into('<I',header,8,6)
            fragments=[bytes(header),struct.pack('<6H',0,1,2,0,1,2)]
        resources.append((name,resource.type_name,fragments))
    path.write_bytes(erp(resources));catalog=Catalog();catalog.mount(path)
    return catalog,family


def inputs():
    rows={}
    for lod in range(2):
        rows[lod]=[]
        for part in range(2):
            source=authored();offset=lod*20+part*10
            source.positions=[(x+offset,y,z) for x,y,z in source.positions]
            rows[lod].append(source)
    return rows


class StaticFamilyTests(unittest.TestCase):
    def test_shared_buffers_materials_and_all_lod_bounds(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.erp';catalog,family=family_fixture(path)
            before=hashlib.sha256(path.read_bytes()).digest();source=inputs()
            report=write_family_test(catalog,family,source,Path(folder)/'output.erp')
            self.assertEqual((report['lods'],report['submeshes'],report['triangles']),(2,4,8))
            self.assertEqual(before,hashlib.sha256(path.read_bytes()).digest())
            check=Catalog();check.mount(Path(folder)/'output.erp')
            for lod in range(2):
                uri=family+f'?lod={lod}&mesh';g=mesh(check,uri)
                self.assertEqual([x['slot'] for x in g.groups],['Surface','Fence'])
                self.assertEqual(g.bounds,[lod*20.,0.,0.,lod*20.+14.,2.,0.])
                data=check.read(uri)
                self.assertEqual(u32(data,76+20),lod*8)
                self.assertEqual(u32(data,76+88+20),lod*8+4)
                self.assertTrue(data.endswith(b'OPAQUE MESH TAIL'))
                draw=76+u32(data,60)
                self.assertEqual((u32(data,draw),u32(data,draw+16)),(123,456))
            model=check.read(family+'?model')
            self.assertEqual(struct.unpack_from('<3f',model,36),(10.,0.,0.))
            self.assertEqual(struct.unpack_from('<3f',model,48),(44.,2.,0.))
            self.assertEqual(model[60:],catalog.read(family+'?model')[60:])
            self.assertEqual(u32(check.read(family+'?vb=0'),8),16)
            self.assertEqual(u32(check.read(family+'?ib=0'),8),24)
            decoded=StaticFamily(check,family).templates[1].source_inputs()
            self.assertEqual(decoded[1].positions,source[1][1].positions)
            self.assertEqual(decoded[1].attributes[6,0],source[1][1].attributes[6,0])
            self.assertEqual(decoded[1].attributes[5,1],source[1][1].attributes[5,1])

    def test_partial_family_missing_parts_and_external_sharing_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.erp';catalog,family=family_fixture(path);template=StaticFamily(catalog,family)
            with self.assertRaisesRegex(ValueError,'complete'):template.templates[0].compile(inputs()[0])
            for bad in ({0:inputs()[0]},{0:inputs()[0],1:[authored()]}):
                with self.assertRaises(ValueError):template.compile(bad)
            with self.assertRaises(ValueError):StaticTemplate(catalog,family+'?lod=0&mesh')
            catalog.by_uri['eaid://other.idf?lod=0&mesh']=catalog.by_uri[family+'?lod=0&mesh']
            read=catalog.read
            catalog.read=lambda name,index=0:read(family+'?lod=0&mesh' if name.startswith('eaid://other') else name,index)
            with self.assertRaisesRegex(ValueError,'outside'):StaticFamily(catalog,family)

    def test_conflicting_companion_ownership_across_lods_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            catalog,family=family_fixture(Path(folder)/'source.erp')
            # A different position group aliases the first LOD's normal/UV buffers.
            alternate=family+'?vb=X';catalog.by_uri[alternate]=catalog.by_uri[family+'?vb=0']
            uri=family+'?lod=1&mesh';changed=catalog.read(uri).replace(b'?vb=0\0',b'?vb=X\0')
            read=catalog.read
            catalog.read=lambda name,index=0:changed if name==uri else read(name,index)
            template=StaticFamily(catalog,family)
            with self.assertRaisesRegex(ValueError,'ownership'):template.compile(inputs())


if __name__=='__main__':unittest.main()
