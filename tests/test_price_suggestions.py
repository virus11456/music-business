import json,tempfile,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from config import Settings
from db import init,connect,now
import price_suggestions,source_queue,platforms,matching,workflow,demo,comparisons
from discogs_client import APIError

RESPONSE={'Mint (M)':{'currency':'USD','value':195.17696629213484},'Near Mint (NM or M-)':{'currency':'USD','value':174.63202247191012},
          'Very Good Plus (VG+)':{'currency':'USD','value':133.5421348314607},'Very Good (VG)':{'currency':'USD','value':92.45224719101124},
          'Poor (P)':{'currency':'USD','value':10.27}}

class Client:
    def __init__(self,fail=()):self.calls=[];self.fail=set(fail)
    def get(self,path,params=None):
        self.calls.append(path)
        if path.rsplit('/',1)[1] in self.fail:raise APIError('404')
        return RESPONSE

class SuggestionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Settings(db_path=Path(self.tmp.name)/'t.db',token='t');init(self.s.db_path)
        platforms.init(self.s);matching.init(self.s);source_queue.init(self.s);workflow.init_workflow(self.s)
        with connect(self.s.db_path) as c:
            c.execute("INSERT INTO platform_candidates(id,platform,external_id,query,title,artist,format,catalog_no,price,currency,price_kind,availability,source_url,captured_at) VALUES(1,'ebay','e1','q','t','','LP','','10','USD','listed','有庫存','https://www.ebay.com/itm/1',?)",(now(),))
            c.execute('INSERT INTO version_searches VALUES(1,?,?,?)',(json.dumps({'release_id':11}),json.dumps([{'release_id':11},{'release_id':12}]),now()))
    def tearDown(self):self.tmp.cleanup()
    def test_parse_keeps_the_four_top_grades_in_one_currency(self):
        self.assertEqual(price_suggestions.parse(RESPONSE),{'currency':'USD','M':195.18,'NM':174.63,'VG+':133.54,'VG':92.45})
        self.assertIsNone(price_suggestions.parse({}));self.assertIsNone(price_suggestions.parse({'Mint (M)':{'currency':'USD','value':0}}))
        self.assertIsNone(price_suggestions.parse({'Mint (M)':{'currency':'USD','value':10},'Very Good (VG)':{'currency':'EUR','value':9}}))
    def test_paired_versions_are_fetched_once_a_week_and_failures_are_counted(self):
        client=Client(fail={'12'})
        result=price_suggestions.refresh(self.s,client)
        self.assertEqual(client.calls,['/marketplace/price_suggestions/11','/marketplace/price_suggestions/12'])
        self.assertEqual((result['saved'],result['failed'],result['due']),(1,1,2))
        again=Client();price_suggestions.refresh(self.s,again)
        self.assertEqual(again.calls,['/marketplace/price_suggestions/12'])  # 11 is fresh; 12 failed before
        later=Client();price_suggestions.refresh(self.s,later,instant=datetime.now(timezone.utc)+timedelta(days=8))
        self.assertEqual(later.calls,['/marketplace/price_suggestions/11','/marketplace/price_suggestions/12'])
        with connect(self.s.db_path) as c:
            self.assertEqual(price_suggestions.stored(c)[11]['VG+'],133.54)
    def test_no_token_means_no_calls(self):
        from dataclasses import replace
        self.assertEqual(price_suggestions.refresh(replace(self.s,token=''),Client())['skipped'],'no_token')

class ComparisonSuggestionTests(unittest.TestCase):
    def test_comparison_rows_carry_the_suggested_prices(self):
        tmp=tempfile.TemporaryDirectory();s=Settings(db_path=Path(tmp.name)/'q.db');init(s.db_path);demo.seed(s);workflow.init_workflow(s);platforms.init(s);matching.init(s)
        from server import release_id,required
        from cli import currency
        with connect(s.db_path) as c:
            workflow.save_offer(c,{'release_id':'900000001','vendor':'Test','source_url':'https://example.com/item','amount':'4500','currency':'JPY','media_cond':'Near Mint (NM or M-)','sleeve_cond':'Near Mint (NM or M-)','version_confirmed':'yes','owned_confirmed':'yes','sale_price':'75','sale_currency':'USD'},release_id,currency,required)
            c.execute('INSERT INTO meta VALUES(?,?)',('price_suggestion:900000001',json.dumps({'at':now(),'currency':'USD','NM':174.63,'VG+':133.54})))
        row=comparisons.build(s)[0]
        self.assertEqual((row['suggest_currency'],row['suggest_nm'],row['suggest_vgp']),('USD',174.63,133.54))
        self.assertEqual(row['net_twd'],'472.00')  # profit basis unchanged
        tmp.cleanup()

if __name__=='__main__':unittest.main()
