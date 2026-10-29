from pathlib import Path
import tempfile,unittest,hashlib
from test_asset_dependencies import fixture
from test_static_family import inputs
from native_fixtures import make_track,pkg,erp,IDENTITY
from alterego_track_editor.native_project import TrackDocument
from alterego_track_editor.static_asset import build_asset
from alterego_track_editor.native.geometry import mesh


def source_track(root):
    catalog,family,binding,mip=fixture(root);folder=catalog.archives[0].path.parent
    archive=make_track(folder);prefix='eaid://environment_package/tracks/input/wep/'
    layer=prefix+'objects.layer'
    archive.write_bytes(erp([(prefix+'input_common.wep','World',[pkg({'layers':[layer]})]),
        (layer,'WOInstances',[pkg({'instances':[{'name':'Board','template':'RenderModel','uniqueid':'one',
          'overrides':{'WorldObject':{'transform':('mat4',IDENTITY)},'Model':{'model':family+'?context=render','mat binding':binding}}}]})]),
        ('eaid://fixture/opaque','Opaque',[b'PRESERVE EXACTLY'])]))
    return folder,family,binding,mip


class NativeAssetUpdateTests(unittest.TestCase):
    def test_embed_new_resources_and_retarget_only_selected_model(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source,family,binding,mip=source_track(root)
            before={p.relative_to(source):hashlib.sha256(p.read_bytes()).digest() for p in source.rglob('*') if p.is_file()}
            doc=TrackDocument(source);target='eaid://fixture/authored.idf'
            resources,report=build_asset(doc.catalog,family,target,inputs(),binding)
            result=doc.write_asset_update(doc.records[0]['id'],target,report['binding'],resources,root/'updated')
            self.assertFalse(result['game_verified']);self.assertFalse(result['collision_generated'])
            updated=TrackDocument(root/'updated')
            self.assertEqual(updated.records[0]['model'],target+'?context=render')
            self.assertEqual(updated.records[0]['binding'],report['binding'])
            self.assertEqual(updated.records[0]['world'],IDENTITY)
            self.assertEqual(mesh(updated.catalog,target+'?lod=1&mesh').triangles,4)
            self.assertEqual(updated.catalog.read('eaid://fixture/opaque'),b'PRESERVE EXACTLY')
            self.assertEqual((root/'updated'/mip.relative_to(source)).read_bytes(),mip.read_bytes())
            for rel,identity in before.items():self.assertEqual(identity,hashlib.sha256((source/rel).read_bytes()).digest())
            updated.close();doc.close()

    def test_conflicting_resource_aborts_before_publication(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source,family,binding,_=source_track(root);doc=TrackDocument(source)
            resources,report=build_asset(doc.catalog,family,'eaid://fixture/authored.idf',inputs(),binding)
            _,original=doc.catalog.get('eaid://fixture/opaque')
            resources.append(('eaid://fixture/opaque',original,[b'CONFLICT']))
            with self.assertRaisesRegex(ValueError,'Conflicting'):
                doc.write_asset_update(doc.records[0]['id'],report['family'],report['binding'],resources,root/'failed')
            self.assertFalse((root/'failed').exists());self.assertEqual(doc.catalog.read('eaid://fixture/opaque'),b'PRESERVE EXACTLY')
            doc.close()


if __name__=='__main__':unittest.main()
