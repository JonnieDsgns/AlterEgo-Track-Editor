from pathlib import Path
import hashlib,json,tempfile,unittest,zipfile
from native_fixtures import make_track,make_canonical_track,IDENTITY
from alterego_track_editor.native_project import TrackDocument
from alterego_track_editor.native.formats.pkg import Document,plain,FormatError
from alterego_track_editor.native.formats.pkg_tree import Tree,patch_edits,selector


def moved(x,y=0.,z=0.):
    m=IDENTITY[:];m[12:15]=[x,y,z];return m


class CanonicalTreeTests(unittest.TestCase):
    def test_stock_layout_round_trip_and_non_canonical_refusal(self):
        with tempfile.TemporaryDirectory() as d:
            _,payload=make_canonical_track(Path(d)/'track')
            tree=Tree(payload);self.assertTrue(tree.canonical);self.assertEqual(tree.to_bytes(),payload)
            make_track(Path(d)/'legacy');doc=TrackDocument(Path(d)/'legacy')
            raw=next(iter(doc.layers.values()))['doc'].data
            self.assertFalse(Tree(raw).canonical)  # trailing opaque bytes, depth-first layout
            doc.close()

    def test_launcher_selectors_and_edit_guards(self):
        self.assertEqual(selector('instances[name=a.b$c].overrides.WorldObject.transform'),
            [('key','instances'),('match','name','a.b$c'),('key','overrides'),('key','WorldObject'),('key','transform')])
        self.assertEqual(selector('[3]'),[('index',3)])
        with self.assertRaises(FormatError):selector('a[name=x')
        with tempfile.TemporaryDirectory() as d:
            _,payload=make_canonical_track(Path(d)/'track')
            for bad in ([{'op':'clone-entry','at':'instances','src':'[name=objects$barrier_a]','as':'objects$board_a'}],
                        [{'op':'clone-entry','at':'instances','src':'[name=missing]','as':'x'}],
                        [{'op':'set-value','path':'instances[0].overrides.WorldObject.transform','value':[1,2,3]}],
                        [{'op':'set-value','path':'instances[0].uniqueid','value':'abc'}],
                        [{'op':'clone-node','src':'x','as':'y'}]):
                with self.assertRaises((FormatError,KeyError)):patch_edits(Tree(payload),bad)


class NativeInsertionTests(unittest.TestCase):
    def test_static_prop_duplicate_full_export(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source,_=make_canonical_track(root/'track');original=source.read_bytes()
            doc=TrackDocument(root/'track')
            by_name={r['name']:r for r in doc.records}
            self.assertIsNone(by_name['objects$barrier_a']['clone_reason'])
            self.assertIn('RenderModel',by_name['objects$GridSlot1']['clone_reason'])
            barrier=by_name['objects$barrier_a'];identity='a1'*16
            replacements=doc.apply({},[{'id':identity,'source':barrier['id'],'world':moved(40,1,2)}])
            result=doc.write_updated(root/'updated',replacements)
            self.assertEqual(len(result['inserted_placements']),1);self.assertFalse(result['game_verified'])
            self.assertIn('no collision',result['limitations'])
            check=TrackDocument(root/'updated');names={r['name']:r for r in check.records}
            self.assertEqual(len(check.records),4)
            new=names['objects$barrier_a_ate_'+identity[:12]]
            self.assertEqual(new['world'][12:15],[40.,1.,2.]);self.assertEqual(new['variants'],barrier['variants'])
            self.assertEqual(new['model'],barrier['model']);self.assertEqual(new['binding'],barrier['binding'])
            self.assertEqual(names['objects$barrier_a']['world'],barrier['world'])
            layer=plain(Document(check.catalog.read(new['layer'])).root)['instances']
            expected=hashlib.md5(f"alterego-track-editor:track:{new['layer']}:{new['name']}".encode()).hexdigest()
            self.assertEqual(layer[3]['uniqueid'],expected);self.assertEqual(layer[3]['overrides']['Render'],layer[0]['overrides']['Render'])
            self.assertTrue(Tree(check.catalog.read(new['layer'])).canonical)
            self.assertEqual(check.catalog.read('eaid://fixture/opaque'),b'untouched')
            self.assertEqual(source.read_bytes(),original)
            check.close();doc.close()

    def test_moves_and_insertions_as_composable_launcher_edits(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);make_canonical_track(root/'track',mirror=True);doc=TrackDocument(root/'track')
            by_name={r['name']:r for r in doc.records};board=by_name['objects$board_a']
            replacements=doc.apply({board['id']:moved(9)},[{'id':'b2'*16,'source':board['id'],'world':moved(11)},
                {'id':'c3'*16,'source':by_name['objects$barrier_a']['id'],'world':moved(13)}])
            uri=board['layer'];edits=doc.layer_edits[uri]
            self.assertEqual([e['op'] for e in edits],['set-value','clone-entry','clone-entry'])
            self.assertEqual(patch_edits(Tree(doc.layers[uri]['doc'].data),edits).to_bytes(),replacements[uri])
            self.assertEqual(doc.write_patch(root/'update.swoftyaddon',replacements,'patch-pkg'),2)
            with zipfile.ZipFile(root/'update.swoftyaddon') as z:
                ops=json.loads(z.read('operations/erp.json'))['ops'];provenance=json.loads(z.read('provenance.json'))
                self.assertFalse(any(n.startswith('fragments/') for n in z.namelist()))
            self.assertEqual({o['op'] for o in ops},{'patch-pkg'})
            self.assertEqual({o['erp'].rsplit('/',1)[-1] for o in ops},{'track_common.erp','mirror.erp'})
            self.assertTrue(all(o['edits']==edits and o['resource']==uri for o in ops))
            self.assertEqual(len(provenance['inserted_placements']),2);self.assertFalse(provenance['game_verified'])
            # Whole-layer replacement carries the same bytes for launchers or users who prefer it.
            doc.write_patch(root/'replace.zip',replacements)
            with zipfile.ZipFile(root/'replace.zip') as z:self.assertEqual(z.read('fragments/0000.bin'),replacements[uri])
            doc.close()

    def test_deterministic_output_and_rejections(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);make_canonical_track(root/'track');outputs=[]
            for _ in range(2):
                doc=TrackDocument(root/'track');barrier=next(r for r in doc.records if r['name']=='objects$barrier_a')
                outputs.append(doc.apply({},[{'id':'d4'*16,'source':barrier['id'],'world':moved(3)}]));doc.close()
            self.assertEqual(outputs[0],outputs[1])
            doc=TrackDocument(root/'track');by_name={r['name']:r for r in doc.records}
            with self.assertRaisesRegex(ValueError,'RenderModel'):
                doc.apply({},[{'id':'e5'*16,'source':by_name['objects$GridSlot1']['id'],'world':moved(1)}])
            barrier=by_name['objects$barrier_a']['id']
            with self.assertRaisesRegex(ValueError,'collides'):
                doc.apply({},[{'id':'f6'*16,'source':barrier,'world':moved(1)},{'id':'f6'*16+'x','source':barrier,'world':moved(2)}])
            with self.assertRaisesRegex(ValueError,'no longer'):doc.apply({},[{'id':'a'*32,'source':'missing','world':moved(1)}])
            with self.assertRaises(Exception):doc.apply({},[{'id':'a'*32,'source':barrier,'world':moved(float('nan'))}])
            doc.close()
            make_track(root/'legacy');legacy=TrackDocument(root/'legacy')
            record=legacy.records[0];replacements=legacy.apply({record['id']:moved(4)})
            self.assertIsNone(legacy.layer_edits[record['layer']])
            with self.assertRaisesRegex(ValueError,'canonical'):legacy.write_patch(root/'composable.zip',replacements,'patch-pkg')
            self.assertFalse((root/'composable.zip').exists())
            self.assertEqual(legacy.write_patch(root/'whole.zip',replacements),1)
            legacy.close()


if __name__=='__main__':unittest.main()


class NativeDeletionTests(unittest.TestCase):
    def test_static_prop_deletion_guards_and_whole_layer_export(self):
        from native_fixtures import make_reference_track
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);make_reference_track(root/'track');doc=TrackDocument(root/'track')
            by_name={r['name']:r for r in doc.records}
            barrier,board,spare=(by_name['objects$'+n] for n in ('barrier_a','board_a','spare_a'))
            with self.assertRaisesRegex(ValueError,'reference'):doc.apply({},deletions=[board['id']])
            with self.assertRaisesRegex(ValueError,'precomputed visibility'):doc.apply({},deletions=[barrier['id']])
            # The spare is deleted while a duplicate of it is inserted; the duplicate keeps its copied entry.
            replacements=doc.apply({},[{'id':'a1'*16,'source':spare['id'],'world':moved(20)}],deletions=[spare['id'],barrier['id']],allow_pvs_deletions=True)
            self.assertEqual({d['name']:d['pvs_listed'] for d in doc.deleted},{'objects$barrier_a':True,'objects$spare_a':False})
            self.assertIsNone(doc.layer_edits[spare['layer']])
            with self.assertRaisesRegex(ValueError,'no deletions'):doc.write_patch(root/'pkg.zip',replacements,'patch-pkg')
            self.assertEqual(doc.write_patch(root/'whole.zip',replacements),1)
            result=doc.write_updated(root/'out'/'track',replacements);self.assertEqual(len(result['deleted_placements']),2)
            check=TrackDocument(root/'out'/'track')
            self.assertEqual(sorted(r['name'] for r in check.records),['objects$board_a','objects$spare_a_ate_'+'a1'*6])
            self.assertEqual(next(r for r in check.records if r['name']=='objects$board_a')['world'],board['world'])
            check.close();doc.close()

    def test_functional_deletion_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            make_canonical_track(Path(d)/'track');doc=TrackDocument(Path(d)/'track')
            grid=next(r for r in doc.records if r['name']=='objects$GridSlot1')
            with self.assertRaisesRegex(ValueError,'only static props'):doc.apply({},deletions=[grid['id']])
            doc.close()
