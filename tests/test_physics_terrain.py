from pathlib import Path
import sys,types,struct,unittest
root=Path(__file__).resolve().parents[1]
if 'alterego_track_editor' not in sys.modules:
    package=types.ModuleType('alterego_track_editor');package.__path__=[str(root/'addon/alterego_track_editor')];sys.modules['alterego_track_editor']=package
from alterego_track_editor.physics_terrain import PhysicsTerrain,build_legacy,KNOWN_CODES


def faces(count=2):
    return [((float(i),0.,0.),(float(i)+.5,0.,0.),(float(i),0.,.5),KNOWN_CODES[i%len(KNOWN_CODES)]) for i in range(count)]


def modern_fixture():
    """Synthetic modern leaf, independently laid out from the read-only contract."""
    vertex=144;node=vertex+6*16;triangle=node+2;refs=(triangle+8+15)&~15
    cell=bytearray(refs+20);struct.pack_into('<I',cell,0,0x20004)
    struct.pack_into('<6f',cell,4,-1,-1,-1,3,3,3)
    for p,v in ((28,2),(32,6),(36,8),(40,vertex),(48,node),(56,triangle),(64,refs)):struct.pack_into('<I',cell,p,v)
    for i,p in enumerate([(0,0,0),(1,0,0),(0,0,1),(1,0,0),(1,0,1),(0,0,1)]):struct.pack_into('<3fI',cell,vertex+i*16,*p,0xaabbccdd)
    for i in range(8):cell[80+i*4:84+i*4]=b'DEFA'
    cell[triangle:triangle+8]=bytes([0xe0,0,1,2,0xa4,3,1,2])
    struct.pack_into('>H',cell,node,0x8000)
    cell[refs:]=struct.pack('<HHBB2HH',0xcdef,0x9876,2,1,0,1,0xffff)+b'INSET123'
    out=bytearray(64);out[:4]=b'JPAK';struct.pack_into('<II',out,8,1,16)
    name=len(out);out.extend(b'synthetic.vcqtc\0');out.extend(b'\0'*(-len(out)%16));offset=len(out);out.extend(cell)
    struct.pack_into('<4I',out,32,name,len(cell),offset,len(cell))
    return bytes(out)


class PhysicsTerrainTests(unittest.TestCase):
    def test_modern_surface_only_edits_preserve_every_other_byte(self):
        raw=modern_fixture();doc=PhysicsTerrain(raw,0x20004)
        self.assertEqual(doc.edit_codes({0:['DEFA','DEFA']}),raw)
        out=doc.edit_codes({0:['RMBL','GRS+']});updated=PhysicsTerrain(out)
        self.assertEqual(updated.cells[0].codes(),['RMBL','GRS+'])
        cell=doc.cells[0];allowed=set(range(cell.offset+80,cell.offset+112))|{cell.offset+cell.triangle+i*4 for i in range(2)}
        self.assertTrue(all(a==b or i in allowed for i,(a,b) in enumerate(zip(raw,out))))
        self.assertEqual(out[cell.offset+cell.refs:],raw[cell.offset+cell.refs:])
        for old,new in zip(doc.cells[0].faces(),updated.cells[0].faces()):self.assertEqual(old[:3]+old[4:],new[:3]+new[4:])

    def test_authored_legacy_spatial_cells_palette_limits_and_no_modern_fallback(self):
        raw=build_legacy(faces(140));doc=PhysicsTerrain(raw,0x20002)
        self.assertEqual(sum(c.triangles for c in doc.cells),140)
        self.assertTrue(all(c.triangles<=1000 and c.vertices<=1023 and len(set(c.codes()))<=8 for c in doc.cells))
        with self.assertRaises(ValueError):PhysicsTerrain(raw,0x20004)
        with self.assertRaises(ValueError):build_legacy([((1e8,0,0),(1e8+1,0,0),(1e8,0,1),'DEFA')])
        with self.assertRaises(ValueError):build_legacy([])
        with self.assertRaises(ValueError):build_legacy([((0,0,0),(1,0,0),(0,0,1),'FAKE')])

    def test_bad_tree_coverage_and_references_rejected(self):
        raw=modern_fixture();doc=PhysicsTerrain(raw);cell=doc.cells[0]
        for offset,value,fmt in [(cell.offset+cell.node,0,'>H'),(cell.offset+cell.refs+8,99,'<H'),(cell.offset,0x12345678,'<I')]:
            bad=bytearray(raw);struct.pack_into(fmt,bad,offset,value)
            with self.assertRaises(ValueError):PhysicsTerrain(bytes(bad))
        with self.assertRaises(ValueError):doc.edit_codes({0:['FAKE','DEFA']})

    def test_duplicate_palette_slots_can_make_room_without_changing_codes(self):
        source=faces(9)
        codes=['DEFA','DEFA',*KNOWN_CODES[1:7],KNOWN_CODES[6]]
        raw=bytearray(build_legacy([(*face[:3],code) for face,code in zip(source,codes)]))
        doc=PhysicsTerrain(bytes(raw));cell=doc.cells[0]
        # Point one DEFA triangle at an explicit duplicate DEFA entry in the spare slot 7.
        index=[f[3] for f in cell.faces()].index(cell.palette.index('DEFA'))
        raw[cell.offset+80+28:cell.offset+84+28]=b'DEFA'
        p=cell.offset+cell.triangle+4*index;raw[p]=(raw[p]&0xe3)|(7<<2)
        doc=PhysicsTerrain(bytes(raw));codes=doc.cells[0].codes();self.assertEqual(doc.edit_codes({0:codes}),bytes(raw))
        desired=codes[:-1]+['SDT+'];out=PhysicsTerrain(doc.edit_codes({0:desired}))
        self.assertEqual(out.cells[0].codes(),desired)
        with self.assertRaises(ValueError):doc.edit_codes({0:list(KNOWN_CODES[:9])})

    def test_opaque_binary_palette_tokens_are_preserved_without_interpretation(self):
        raw=bytearray(modern_fixture());base=PhysicsTerrain(bytes(raw)).cells[0].offset
        raw[base+80:base+84]=b'\0'*4
        doc=PhysicsTerrain(bytes(raw));codes=doc.cells[0].codes()
        self.assertEqual(codes[0],'HEX_00000000')
        self.assertEqual(doc.edit_codes({0:codes}),bytes(raw))
        out=PhysicsTerrain(doc.edit_codes({0:[codes[0],'RMBL']}))
        self.assertEqual(out.cells[0].codes(),[codes[0],'RMBL'])


if __name__=='__main__':unittest.main()
