import importlib
import io
import numpy as np
from PIL import Image
import unittest
from test_native_project import package
codec=importlib.import_module(package.__name__+'.image_codec')


class PreviewCodecTests(unittest.TestCase):
    def test_bc_colour_and_alpha_match_reference(self):
        rng=np.random.default_rng(42)
        for fmt,kind in ((52,1),(55,3),(62,2),(63,4)):
            stride=8 if kind in (1,4) else 16
            raw=rng.integers(0,256,size=4*stride,dtype=np.uint8).tobytes()
            result=codec.decode_image(raw,8,8,fmt).pixels
            name={1:'DXT1',2:'DXT3',3:'DXT5',4:'BC4'}[kind]
            reference=np.asarray(Image.frombytes('L' if kind==4 else 'RGBA',(8,8),raw,'bcn',(kind,name)).convert('RGBA'))
            # Encoder/decoder endpoint expansion can differ by one integer.
            self.assertLessEqual(np.abs(result.astype(int)-reference.astype(int)).max(),1)
            output=io.BytesIO();codec.decode_image(raw,8,8,fmt).save(output)
            self.assertEqual(Image.open(io.BytesIO(output.getvalue())).size,(8,8))

    def test_png_filters_and_terrain_facade(self):
        pixels=np.random.default_rng(3).integers(0,256,size=(8,8,4),dtype=np.uint8)
        output=io.BytesIO();Image.fromarray(pixels).save(output,format='PNG')
        result=codec.ImageFacade.open(io.BytesIO(output.getvalue())).convert('RGBA')
        np.testing.assert_array_equal(np.asarray(result),pixels)
        geometry=importlib.import_module(package.__name__+'.native.geometry')
        terrain=importlib.import_module(package.__name__+'.native.terrain_materials')
        old=terrain.Image;terrain.Image=codec.ImageFacade
        try:
            g=geometry.combine([([(0,0,0),(1,0,0),(0,0,1)],[(0,1,0)]*3,[0,1,2],{0:[(0,0),(1,0),(0,1)],1:[(0,0),(1,0),(0,1)]})])
            def png(colour):
                out=io.BytesIO();codec.PreviewImage(np.full((4,4,4),colour,dtype=np.uint8)).save(out);return out.getvalue()
            class Service:
                def __init__(self):self.images={'red':png((255,0,0,255)),'mask':png((0,0,0,255))}
                def texture_key(self,key):return key
                def png(self,key):return self.images[key]() if callable(self.images[key]) else self.images[key]
                def register_texture(self,key,loader):self.images[key]=loader
                def note(self,*args):pass
            service=Service();material={'id':'terrain','shader':'terrain_4way_blend','sourceTextures':{'me_blendMap':'mask',**{'me_layer'+str(i)+'_albedoMap':'red' for i in range(1,5)}},'sourceValues':{}}
            baked=terrain.bake_terrain(service,g,material,'fixture',lambda:g,size=16)
            image=codec.ImageFacade.open(io.BytesIO(service.png(baked['base'])))
            self.assertGreater(image.pixels[3,3,0],240)
            self.assertLess(image.pixels[3,3,1],5)
        finally:terrain.Image=old

    def test_preview_limits_and_unsupported_format(self):
        for args in ((b'',4097,1,52),(b'',4,4,52),(b'0'*16,4,4,69)):
            with self.assertRaises(ValueError):codec.decode_image(*args)

if __name__=='__main__':unittest.main()
