from pathlib import Path
import tempfile,unittest
from native_fixtures import make_race_track,IDENTITY
from alterego_track_editor.native_project import TrackDocument
from alterego_track_editor.native.formats.pkg import Document,plain
from alterego_track_editor.native.formats.pkg_tree import Tree,patch_edits


def at(x):
    m=IDENTITY[:];m[12]=x;return m


class RacePlacementTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.root=Path(self.folder.name);make_race_track(self.root/'track')
        self.doc=TrackDocument(self.root/'track');self.by_name={r['name']:r for r in self.doc.records}

    def tearDown(self):
        self.doc.close();self.folder.cleanup()

    def entries(self,data):
        return {i['name']:i for i in plain(Document(data).root)['instances']}

    def test_numbering_follows_every_world_of_the_layer(self):
        slot=self.by_name['myteam$GridSlot3']
        replacements=self.doc.apply({},[{'id':'a'*32,'source':slot['id'],'world':at(24),'race':True}])
        new=self.entries(replacements[slot['layer']])['myteam$GridSlot4']
        self.assertEqual(new['overrides']['VehPlacement'],{'Group':'GridWheelMarker','Id':4})
        self.assertEqual(new['overrides']['WorldObject']['transform'][12],24.)
        edits=self.doc.layer_edits[slot['layer']]
        self.assertEqual(edits[0]['set']['overrides.VehPlacement.Id'],4)
        self.assertEqual(patch_edits(Tree(self.doc.layers[slot['layer']]['doc'].data),edits).to_bytes(),replacements[slot['layer']])
        with self.assertRaisesRegex(ValueError,'numbering gap in f1'):
            self.doc.apply({},[{'id':'b'*32,'source':self.by_name['base$GridSlot2']['id'],'world':at(30),'race':True}])

    def test_garages_reference_new_pit_garages_in_one_export(self):
        garage,pit=self.by_name['base$F1Garage2'],self.by_name['base$PitGarage4']
        specs=[{'id':'c'*32,'source':garage['id'],'world':at(130),'race':True,'order':3},
               {'id':'d'*32,'source':pit['id'],'world':at(125),'race':True,'order':1},
               {'id':'e'*32,'source':pit['id'],'world':at(130),'race':True,'order':2},
               {'id':'f'*32,'source':self.by_name['base$PitBox2']['id'],'world':at(230),'race':True}]
        replacements=self.doc.apply({},specs);entries=self.entries(replacements[garage['layer']])
        self.assertEqual([entries[f'base$PitGarage{n}']['overrides']['WorldObject']['transform'][12] for n in (5,6)],[125.,130.])
        self.assertEqual(entries['base$F1Garage3']['overrides']['F1Garage'],{'id':3,
            'left car placement':entries['base$PitGarage5']['uniqueid'],'right car placement':entries['base$PitGarage6']['uniqueid']})
        self.assertEqual(entries['base$PitBox3']['overrides']['VehPlacement']['Id'],3)
        self.assertEqual(len(self.doc.inserted),4)

    def test_invalid_sources_and_missing_pit_garages_are_refused(self):
        with self.assertRaisesRegex(ValueError,'explicit Id'):
            self.doc.apply({},[{'id':'a'*32,'source':self.by_name['base$GridSlot1']['id'],'world':at(1),'race':True}])
        with self.assertRaisesRegex(ValueError,'PitGarage5'):
            self.doc.apply({},[{'id':'a'*32,'source':self.by_name['base$F1Garage2']['id'],'world':at(1),'race':True}])
        with self.assertRaisesRegex(ValueError,'not a numbered|Not a numbered|RenderModel'):
            self.doc.apply({},[{'id':'a'*32,'source':self.by_name['base$GridSlot2']['id'],'world':at(1)}])


if __name__=='__main__':unittest.main()
