from pathlib import Path
import json,tempfile,unittest,zipfile
from native_fixtures import make_route_track,bxml
from alterego_track_editor.native_project import TrackDocument
from alterego_track_editor.native_routes import fraction_text
from alterego_track_editor.native.formats.bxml import Document,FormatError


class BxmlTests(unittest.TestCase):
    def test_round_trip_text_and_rejections(self):
        data=bxml(('root',[('a','1')],[('child',[],[])]))
        text=data[:-18]+b'\x08\x00\x01\x00\x00\x00abc\0'+data[-18:]  # text record inside root keeps raw bytes
        for raw in (data,text):self.assertEqual(Document(raw).to_bytes(),raw)
        for bad in (b'\x01BXM',data[:-18],data.replace(b'a\x001\x00',b'a\x00\x00\x00')):
            with self.assertRaises(FormatError):Document(bad)

    def test_fraction_text(self):
        self.assertEqual([fraction_text(v) for v in (0,1,0.3215,0.123456789)],['0','1','0.3215','0.123457'])
        for bad in (-0.1,1.1,float('nan')):
            with self.assertRaises(ValueError):fraction_text(bad)


class RouteDataTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.path,self.tm=make_route_track(Path(self.folder.name)/'track')
        self.doc=TrackDocument(Path(self.folder.name)/'track');self.routes=self.doc.routes()

    def tearDown(self):
        self.doc.close();self.folder.cleanup()

    def index(self,name):return next(m['index'] for m in self.routes.markup if m['name']==name)

    def test_geometry_preview_helpers(self):
        main,pit=self.routes.splines['maintrack'],self.routes.splines['pit_1']
        self.assertTrue(main.closed);self.assertFalse(pit.closed);self.assertAlmostEqual(main.length,400.0)
        self.assertEqual([round(v,6) for v in main.point(0.25)],[100.0,0.0,0.0])
        fraction,distance=main.nearest([50,3,-2]);self.assertAlmostEqual(fraction,0.125);self.assertLess(distance,4)
        wrapped=main.segment(0.9,0.1);self.assertAlmostEqual(wrapped[0][2],40.0);self.assertAlmostEqual(wrapped[-1][0],40.0)
        self.assertEqual(self.routes.ai_line('track','racing_line')[1],[10.0,0.0,0.5])
        self.assertEqual(self.routes.ai_line('track','left_track_limit')[0],[0.0,0.0,-5.0])
        self.assertEqual({m['name'] for m in self.routes.markup if not m['gameplay']},{'audio_tunnel'})

    def test_markup_edits_and_rules(self):
        s1,s2,drs=self.index('sector1'),self.index('sector2'),self.index('drs_activation_1')
        data=self.routes.write_markup({s1:(0,0.35),s2:(0.35,0.7),drs:(0.95,0.12)})
        rows={e.get('Name'):(e.get('Start'),e.get('End')) for e in Document(data).root.elements('MarkupList')[0].elements('MarkupElement')}
        self.assertEqual(rows,{'sector1':('0','0.35'),'sector2':('0.35','0.7'),'sector3':('0.7','1'),'drs_activation_1':('0.95','0.12'),
            'pit_limiter_on':('0.1','0.9'),'audio_tunnel':('0.4','0.5')})
        self.assertEqual(self.routes.write_markup({}),self.tm)
        cases=[({s1:(0,0.35)},'chained'),({s1:(0.01,0.3)},'lap start'),({self.index('audio_tunnel'):(0.4,0.6)},'gameplay'),
               ({self.index('pit_limiter_on'):(0.9,0.1)},'closed'),({s1:(0,0.8),s2:(0.8,0.7)},'lap order')]
        for edits,message in cases:
            with self.assertRaisesRegex(ValueError,message):self.routes.write_markup(edits)

    def test_export_full_and_update_addon(self):
        root=Path(self.folder.name);drs=self.index('drs_activation_1')
        replacements=self.doc.apply({},markup={drs:(0.92,0.08)})
        self.doc.write_updated(root/'out'/'track',replacements)
        check=TrackDocument(root/'out'/'track');self.assertEqual(check.routes().markup[drs]['start'],0.92);check.close()
        self.doc.write_patch(root/'update.zip',replacements,'patch-pkg')
        with zipfile.ZipFile(root/'update.zip') as z:
            ops=json.loads(z.read('operations/erp.json'))['ops'];provenance=json.loads(z.read('provenance.json'))
            self.assertEqual([o['op'] for o in ops],['replace-resource']);self.assertEqual(z.read(ops[0]['source']),replacements[self.routes.uris['TM']])
        self.assertEqual(provenance['replaced_resources'],[self.routes.uris['TM']])


if __name__=='__main__':unittest.main()
