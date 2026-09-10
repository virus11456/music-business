import unittest
from source_match import evidence

class SourceEvidenceTests(unittest.TestCase):
 def setUp(self):
  self.release={'title':'Rubber Soul = ラバー・ソウル','format':'Vinyl','catno':'PCS 3075'}
  self.source={'title':'The Beatles Rubber Soul LP used VG','format':'LP','catalog_no':''}
 def test_same_album_condition_does_not_matter(self):
  self.assertTrue(evidence(self.source,self.release))
 def test_other_album_is_not_a_match(self):
  self.assertFalse(evidence({**self.source,'title':'The Beatles Abbey Road LP'},self.release))
 def test_merchandise_excluded_even_with_album_title(self):
  self.assertFalse(evidence({**self.source,'title':'Rubber Soul T-shirt'},self.release))
 def test_explicit_format_conflict_overrides_catalog(self):
  self.assertFalse(evidence({**self.source,'format':'CD','catalog_no':'PCS-3075'},self.release))
 def test_japanese_alias(self):
  self.assertTrue(evidence({**self.source,'title':'ビートルズ ラバー・ソウル LP'},self.release))
 def test_catalog_allows_unrecognized_translation(self):
  self.assertTrue(evidence({**self.source,'title':'披頭四 橡皮靈魂','catalog_no':'PCS-3075'},self.release))
 def test_short_title_does_not_match_everything(self):
  self.assertFalse(evidence(self.source,{**self.release,'title':'1'}))
