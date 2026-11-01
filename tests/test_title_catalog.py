import unittest
from source_match import evidence,title_catalog

RELEASE={'release_id':1,'artist':'Tatsuro Yamashita','title':'For You','catno':'RAL-8801','format':'Vinyl'}
def item(title):return {'platform':'yahoo_jp','title':title,'artist':'','format':'未確認','catalog_no':'','external_id':'x'}

class TitleCatalogTests(unittest.TestCase):
    def test_number_without_hyphen_or_split_by_a_space_is_found_as_a_whole_token(self):
        self.assertEqual(title_catalog('国内盤 山下達郎 FOR YOU AIR RAL8801 1LP','RAL-8801'),'RAL-8801')
        self.assertEqual(title_catalog('帯付RAL 8801 LP','RAL-8801'),'RAL-8801')
        self.assertEqual(title_catalog('TOCP-123 CD','TOCP-1'),'')        # too short and not the whole token
        self.assertEqual(title_catalog('RAL88010 LP','RAL-8801'),'')
        self.assertEqual(title_catalog('12345 LP','12345'),'')            # digits alone are not a catalogue number
    def test_title_number_becomes_catalogue_evidence(self):
        reasons=evidence(item('山下達郎 FOR YOU RAL8801 LP'),RELEASE)
        self.assertIn('規格品番一致，仍需核對壓片',reasons);self.assertIn('唱片編號取自賣場標題，仍需核對實物',reasons)
        self.assertNotIn('規格品番一致，仍需核對壓片',evidence(item('山下達郎 FOR YOU LP'),RELEASE))

if __name__=='__main__':unittest.main()
