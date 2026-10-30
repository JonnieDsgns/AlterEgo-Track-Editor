from pathlib import Path
import struct,sys,types,unittest
root=Path(__file__).resolve().parents[1]
if 'alterego_track_editor' not in sys.modules:
    package=types.ModuleType('alterego_track_editor');package.__path__=[str(root/'addon/alterego_track_editor')];sys.modules['alterego_track_editor']=package
from alterego_track_editor.physics_terrain import PhysicsTerrain,build_legacy,triangle_soup,code_words,CHUNK_TRIANGLES,CHUNK_VERTICES
from test_physics_terrain import modern_fixture

CODES=['SDT+','GRS+','RMBL','SCON']


def grid(size=60,step=4.0,codes=CODES):
    faces=[]
    for i in range(size):
        for j in range(size):
            x,z=i*step,j*step;code=codes[(i//7+j//5)%len(codes)];y=0.1*((i*j)%7)
            faces.append(((x,y,z),(x+step,y,z),(x,y,z+step),code,(0xff000000|i,0xff000000|j,0xff123456)))
            faces.append(((x+step,y,z),(x+step,y,z+step),(x,y,z+step),code))
    return faces


def tree(cell):
    """(root internal?, leaf depths, leaf reference counts) by walking the legacy node words."""
    data=cell.data;depths=[];sizes=[];stack=[(0,0)]
    root=struct.unpack_from('>H',data,cell.node)[0]
    while stack:
        index,depth=stack.pop();word=struct.unpack_from('>H',data,cell.node+2*index)[0]
        if word<0x8000:stack.extend((k,depth+1) for k in range(word,word+4));continue
        if word==0xffff:continue
        p=cell.refs+(word&0x7fff)+2;count=1
        while data[p]!=255:count+=1;p+=1
        depths.append(depth);sizes.append((depth,count))
    return root<0x8000,depths,sizes


class LegacyRebuildTests(unittest.TestCase):
    def test_layout_matches_game_tested_legacy_conventions(self):
        source=grid();raw=build_legacy(source,codes=CODES+['HDG+'],words={'GRS+':0xff5f83b6})
        doc=PhysicsTerrain(raw,0x20002)
        self.assertGreater(len(doc.cells),1)
        self.assertEqual(struct.unpack_from('<I',raw,0x14)[0],32+32*len(doc.cells))  # name-table offset, as in stock files
        self.assertEqual(sum(c.triangles for c in doc.cells),len(source))
        for cell in doc.cells:
            self.assertTrue(cell.name.startswith('qt') and cell.name.endswith('.vcqtc'))
            self.assertLessEqual(cell.triangles,CHUNK_TRIANGLES);self.assertLessEqual(cell.vertices,CHUNK_VERTICES)
            used=sorted({f[3] for f in cell.faces()});self.assertEqual(used,list(range(len(used))))  # used slots are a prefix
            self.assertTrue(set(cell.palette)<=set(CODES+['HDG+']))
            self.assertEqual({f[4] for f in cell.faces()},{7})
            internal,depths,sizes=tree(cell)
            self.assertTrue(internal);self.assertLessEqual(max(depths),6)
            self.assertTrue(all(count<=24 or depth==6 for depth,count in sizes))
        words={}
        for cell in doc.cells:
            positions=cell.positions()
            for a,b,c,slot,_ in cell.faces():
                for v in (a,b,c):words.setdefault((positions[v],cell.palette[slot]),set()).add(struct.unpack_from('<I',cell.data,144+v*16+12)[0])
        self.assertIn(0xff000003,words[((12.0,0.0,0.0),'SDT+')])  # explicit per-vertex words kept
        self.assertTrue(any(0xff5f83b6 in w for (p,code),w in words.items() if code=='GRS+'))  # per-code default

    def test_dense_overlapping_geometry_and_rejections(self):
        stacked=[((0.,float(i),0.),(1.,float(i),0.),(0.,float(i),1.),'SDT+') for i in range(2500)]
        doc=PhysicsTerrain(build_legacy(stacked,codes=['SDT+']),0x20002)
        self.assertEqual(sum(c.triangles for c in doc.cells),2500);self.assertGreaterEqual(len(doc.cells),3)
        with self.assertRaisesRegex(ValueError,'not used by the base'):build_legacy(grid(10),codes=['SDT+'])
        with self.assertRaises(ValueError):build_legacy([((0,0,0),(0,0,0),(1,0,0),'SDT+')],codes=['SDT+'])

    def test_modern_native_soup_round_trips_into_legacy(self):
        modern=PhysicsTerrain(modern_fixture(),0x20004)
        soup=list(triangle_soup(modern.cells));self.assertEqual(len(soup),2)
        self.assertEqual(code_words(modern),{'DEFA':0xaabbccdd})
        legacy=PhysicsTerrain(build_legacy(soup,codes=['DEFA']),0x20002)
        rebuilt=list(triangle_soup(legacy.cells))
        key=lambda t:sorted([t[0],t[1],t[2]])+[t[3]]
        self.assertEqual(sorted(map(key,rebuilt)),sorted(map(key,soup)))
        self.assertEqual({w for t in rebuilt for w in t[4]},{0xaabbccdd})


if __name__=='__main__':unittest.main()
