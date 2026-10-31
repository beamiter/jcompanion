#!/usr/bin/env python3
"""PNG-oracle regressions, not GUI/native/physical proof or body destruction."""
from pathlib import Path
import unittest
from PIL import Image
from native_windows import cat_components

FIXTURE=Path(__file__).with_name('fixtures')/'native-cat-guard-failure.png'

class NativeBodyClassifier(unittest.TestCase):
    def test_one_native_cat_with_detached_dim_cloud_is_one_body(self):
        with Image.open(FIXTURE) as image:
            self.assertEqual(len(cat_components(image)),1)

    def test_dim_effect_alone_is_not_another_body(self):
        with Image.open(FIXTURE) as image:
            self.assertEqual(cat_components(image.crop((0,0,image.width,73))),[])

    def test_two_close_body_footprints_remain_two(self):
        # Extract each actual body footprint, then place two copies 24 pixels
        # apart. Increasing the spatial join radius to hide the cloud must not
        # merge these into one. The copies are explicitly synthetic oracle data.
        with Image.open(FIXTURE) as image:
            body=image.crop((28,79,202,157)).convert('RGB')
            canvas=Image.new('RGB',(body.width*2+24,body.height),(14,21,30))
            canvas.paste(body,(0,0));canvas.paste(body,(body.width+24,0))
            self.assertEqual(len(cat_components(canvas)),2)

    def test_two_organisms_with_their_own_clouds_remain_two(self):
        with Image.open(FIXTURE) as image:
            image=image.convert('RGB')
            canvas=Image.new('RGB',(image.width*2+24,image.height),(14,21,30))
            canvas.paste(image,(0,0));canvas.paste(image,(image.width+24,0))
            self.assertEqual(len(cat_components(canvas)),2)

if __name__=='__main__':unittest.main(verbosity=2)
