from pathlib import Path
import hashlib
import struct
import sys
import tempfile
import types
import unittest

ROOT=Path(__file__).resolve().parents[1]
# Pure modules without importing Blender's package entry point.
if 'alterego_track_editor' not in sys.modules:
    package=types.ModuleType('alterego_track_editor');package.__path__=[str(ROOT/'addon/alterego_track_editor')]
    sys.modules['alterego_track_editor']=package
from alterego_track_editor.static_geometry import StaticInput,StaticTemplate,write_test
from alterego_track_editor.native.storage import Catalog
from alterego_track_editor.native.geometry import mesh
from native_fixtures import erp


def static_fixture(path):
    family='eaid://fixture/board.idf';uri=family+'?lod=0&mesh'
    keys=[(1,0),(2,0),(3,0),(5,0),(5,1),(6,0)]
    vb=[family+'?vb='+str(i) for i in range(len(keys))];ib=family+'?ib=0'
    d=bytearray(164);struct.pack_into('<3I',d,0,1,len(vb),1)
    struct.pack_into('<I',d,76,len(keys));struct.pack_into('<3I',d,88,0,3,0)
    struct.pack_into('<4f',d,100,0,0,0,2)
    struct.pack_into('<I',d,124,0)
    for i in range(len(keys)):struct.pack_into('<I',d,132+4*i,i)
    def append(raw):off=len(d);d.extend(raw);return off-76
    vbo=append(b''.join((s+'\0').encode() for s in vb));ibo=append((ib+'\0').encode())
    material=append(b'Surface\0');end=len(d)-76
    declarations=append(b''.join(struct.pack('<5I',0,0,*key,47 if key==(1,0) else 0) for key in keys))
    bindings=append(b''.join(struct.pack('<2I',0,i) for i in range(len(keys))))
    draw=append(struct.pack('<4I',123,0,0,3))
    for at,val in [(20,vbo),(24,ibo),(28,material),(32,end),(36,len(keys)),(40,declarations),(44,bindings),(56,1),(60,draw)]:
        struct.pack_into('<I',d,at,val)
    d.extend(b'OPAQUE MESH TAIL')
    model=bytearray(72);struct.pack_into('<I',model,0,1);struct.pack_into('<I',model,12,1)
    model.extend(uri.encode()+b'\0OPAQUE MODEL TAIL')
    render=bytearray(252);struct.pack_into('<HH',render,0,2,0)
    for i in range(2):
        p=12+120*i;struct.pack_into('<i',render,p+4,i-1)
        struct.pack_into('<10f',render,p+8,0,0,0,0,0,0,1,1,1,1)
        struct.pack_into('<I',render,p+112,1)
    # A translated render-local transform exercises model-space bounds.
    struct.pack_into('<f',render,12+120+8,10)
    resources=[(uri,'Mesh',[bytes(d)]),(family+'?model','Model',[bytes(model)]),(family+'?render','Render',[bytes(render)])]
    positions=[(0.,0.,0.),(1.,0.,0.),(0.,1.,0.)]
    for key,name in zip(keys,vb):
        stride,fmt=(12,39) if key==(1,0) else (4,14) if key==(6,0) else (8,35)
        data=b''.join(struct.pack('<3f',*p) for p in positions) if key==(1,0) else b'\0'*(stride*3)
        resources.append((name,'Buffer',[struct.pack('<4I',4361,stride,3,fmt),data]))
    resources.extend([(ib,'Buffer',[struct.pack('<4I',0,2,3,19),struct.pack('<3H',0,1,2)]),('eaid://fixture/opaque','Opaque',[b'KEEP ME'])])
    path.write_bytes(erp(resources));catalog=Catalog();catalog.mount(path)
    return catalog,uri


def authored():
    return StaticInput([(0.,0.,0.),(4.,0.,0.),(4.,2.,0.),(0.,2.,0.)],[0,1,2,0,2,3],{
        (2,0):[(0.,0.,1.)]*4,(3,0):[(1.,0.,0.,1.)]*4,
        (5,0):[(0.,0.,0.,0.),(1.,0.,0.,0.),(1.,1.,0.,0.),(0.,1.,0.,0.)],
        (5,1):[(.25,.75,.5,1.)]*4,(6,0):[(255,128,0,255)]*4})


class StaticGeometryTests(unittest.TestCase):
    def test_topology_buffers_bounds_and_opaque_readback(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.erp';catalog,uri=static_fixture(source)
            before=hashlib.sha256(source.read_bytes()).hexdigest();template=StaticTemplate(catalog,uri)
            output=Path(folder)/'output.erp';report=write_test(catalog,uri,authored(),output)
            self.assertEqual(report['triangles'],2);self.assertFalse(report['game_verified'])
            self.assertEqual(before,hashlib.sha256(source.read_bytes()).hexdigest())
            check=Catalog();check.mount(output);g=mesh(check,uri)
            self.assertEqual(g.bounds,[0.,0.,0.,4.,2.,0.]);self.assertEqual(g.groups[0]['slot'],'Surface')
            self.assertEqual(check.read('eaid://fixture/opaque'),b'KEEP ME')
            self.assertTrue(check.read(uri).endswith(b'OPAQUE MESH TAIL'))
            self.assertTrue(check.read(template.family+'?model').endswith(b'OPAQUE MODEL TAIL'))
            model=check.read(template.family+'?model')
            self.assertEqual(struct.unpack_from('<3f',model,36),(10.,0.,0.))
            self.assertEqual(struct.unpack_from('<3f',model,48),(14.,2.,0.))
            self.assertEqual(check.read(template.family+'?render'),catalog.read(template.family+'?render'))
            with self.assertRaises(ValueError):write_test(catalog,uri,authored(),source)
            with self.assertRaises(ValueError):write_test(catalog,uri,authored(),output)

    def test_bad_inputs_and_profiles_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            catalog,uri=static_fixture(Path(folder)/'source.erp');template=StaticTemplate(catalog,uri)
            mutations=[lambda x:x.indices.__setitem__(0,999),lambda x:x.positions.__setitem__(0,(float('nan'),0,0)),
                lambda x:x.attributes.pop((5,1)),lambda x:x.attributes[(2,0)].__setitem__(0,(0.,0.,2.)),
                lambda x:x.attributes[(5,0)].__setitem__(0,(1e9,0.,0.,0.)),
                lambda x:x.positions.__setitem__(1,x.positions[0]),
                lambda x:x.attributes[(3,0)].__setitem__(0,(0.,0.,0.,1.))]
            for mutation in mutations:
                data=authored();mutation(data)
                with self.assertRaises(ValueError):template.compile(data)
            for field,value in [(0,2),(56,2)]:
                raw=bytearray(catalog.read(uri));struct.pack_into('<I',raw,field,value)
                cat=Catalog();cat.mount(Path(folder)/'source.erp')
                original=cat.read;cat.read=lambda name,index=0,raw=bytes(raw):raw if name==uri else original(name,index)
                with self.assertRaises(ValueError):StaticTemplate(cat,uri)


if __name__=='__main__':unittest.main()
