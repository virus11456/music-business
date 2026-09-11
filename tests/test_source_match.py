import unittest
from source_match import evidence,source_catalog

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
 def test_unknown_metadata_uses_title_and_rejects_cross_format(self):
  vinyl={**self.source,'format':'未確認','title':'披頭士黑膠唱片 TheBeatles RubberSoul LP'}
  self.assertTrue(evidence(vinyl,self.release))
  self.assertFalse(evidence(vinyl,{**self.release,'format':'CD'}))
 def test_unknown_and_mixed_formats_are_not_admitted(self):
  for title in ['Rubber Soul','Rubber Soul CD + LP','Rubber Soul 卡帶 CD']:
   self.assertFalse(evidence({**self.source,'format':'未確認','title':title},self.release))
 def test_cassette_only_pairs_with_cassette(self):
  source={**self.source,'format':'未確認','title':'Rubber Soul 卡帶'}
  self.assertTrue(evidence(source,{**self.release,'format':'Cassette'}))
  self.assertFalse(evidence(source,{**self.release,'format':'CD'}))
 def test_label_supports_but_never_overrides_wrong_catalog(self):
  source={**self.source,'title':'Rubber Soul Parlophone LP','catalog_no':'PCS 3075'}
  release={**self.release,'labels':'Parlophone'}
  self.assertTrue(any('Label' in x for x in evidence(source,release)))
  self.assertFalse(evidence({**source,'catalog_no':'OTHER123'},release))

 def test_title_catalog_rejects_a_different_pressing(self):
  source={**self.source,'title':'The Beatles Rubber Soul LP AP-8156'}
  self.assertEqual(source_catalog(source),'AP-8156')
  self.assertFalse(evidence(source,self.release))
  self.assertTrue(evidence(source,{**self.release,'catno':'AP 8156'}))
 def test_title_catalog_is_conservative_and_normalizes_fullwidth(self):
  for title in ['Rubber Soul 2015 180g LP','Rubber Soul CD-123','Rubber Soul AP-8156 PCS-3075','Rubber Soul AP-8156-2','Rubber Soul XAP-8156B']:
   self.assertEqual(source_catalog({**self.source,'title':title}),'')
  self.assertEqual(source_catalog({**self.source,'title':'Rubber Soul ＡＰ－８１５６'}),'AP-8156')
  self.assertEqual(source_catalog({**self.source,'title':'AP-8156','catalog_no':'PCS 3075'}),'PCS 3075')
