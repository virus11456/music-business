import json,tempfile,unittest
from pathlib import Path
from dataclasses import replace
from urllib.error import HTTPError
from config import Settings
from db import init,connect
import platform_health,sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'scripts'))
import platform_probe

def stats(success=0,empty=0,failed=0,items=0,errors=None):
    return {'success':success,'empty':empty,'failed':failed,'items':items,'errors':errors or {}}

class HealthTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Settings(db_path=Path(self.tmp.name)/'t.db');init(self.s.db_path)
        self.sent=[]
    def tearDown(self):self.tmp.cleanup()
    def send(self,settings,text):self.sent.append(text)
    def test_failing_platform_is_reported_once_and_recovery_is_reported(self):
        s=replace(self.s,telegram_token='t',telegram_chat='c')
        first=platform_health.record(s,{'yahoo_jp':stats(failed=100,errors={'ValueError':100}),'ebay':stats(success=89,empty=11,items=2611),'tower':stats(failed=3)},sender=self.send)
        self.assertEqual(first,{'changes':[{'platform':'yahoo_jp','status':'failing'}],'notified':True})  # tower: too few searches
        self.assertIn('Yahoo 日本：100/100 次搜尋失敗（ValueError 100 次）',self.sent[0])
        again=platform_health.record(s,{'yahoo_jp':stats(failed=90,success=10)},sender=self.send)
        self.assertEqual(again['changes'],[]);self.assertEqual(len(self.sent),1)
        healed=platform_health.record(s,{'yahoo_jp':stats(success=95,empty=5,items=4000)},sender=self.send)
        self.assertEqual(healed['changes'],[{'platform':'yahoo_jp','status':'ok'}]);self.assertIn('Yahoo 日本 已恢復',self.sent[1])
        state={e['platform']:e for e in platform_health.state(s)}
        self.assertEqual((state['yahoo_jp']['status'],state['ebay']['status'],state['ebay']['items']),('ok','ok',2611))
    def test_failing_since_is_kept_while_the_platform_stays_down(self):
        platform_health.record(self.s,{'ruten':stats(failed=68,success=32)},instant=__import__('datetime').datetime(2026,11,1,tzinfo=__import__('datetime').timezone.utc))
        platform_health.record(self.s,{'ruten':stats(failed=60,success=40)})
        entry=platform_health.state(self.s)[0]
        self.assertEqual((entry['status'],entry['since'][:10],entry['failed']),('failing','2026-11-01',60))
    def test_without_telegram_nothing_is_sent_but_state_is_saved(self):
        result=platform_health.record(self.s,{'ruten':stats(failed=10)},sender=self.send)
        self.assertEqual((result['notified'],self.sent),(False,[]))
        self.assertEqual(platform_health.state(self.s)[0]['status'],'failing')
    def test_health_state_survives_in_the_sheet_meta_prefixes(self):
        import sheet_records
        self.assertTrue(sheet_records.allowed_meta('platform_health:ruten'))

class ProbeTests(unittest.TestCase):
    def test_probe_classifies_blocked_broken_empty_and_ok(self):
        def page(items):
            listing={'items':items}
            data={'props':{'pageProps':{'initialState':{'search':{'items':{'listing':listing}}}}}}
            return '<script id="__NEXT_DATA__" type="application/json">'+json.dumps(data)+'</script>'
        page,empty=page([{'auctionId':'a1','title':'For You','price':1000,'isFixedPrice':False}]),page([])
        self.assertEqual(platform_probe.probe('yahoo_jp',fetcher=lambda u:page)['status'],'ok')
        self.assertEqual(platform_probe.probe('yahoo_jp',fetcher=lambda u:'<html>changed</html>')['status'],'broken')
        def blocked(u):raise HTTPError(u,403,'no',{},None)
        self.assertEqual(platform_probe.probe('tower',fetcher=blocked),{'platform':'tower','status':'blocked','error':'HTTP 403','seconds':0.0})
        self.assertEqual(platform_probe.probe('yahoo_jp',fetcher=lambda u:empty)['status'],'empty')
        self.assertEqual(platform_probe.probe('ebay')['status'],'skipped')
        from types import SimpleNamespace
        only_rakuten=SimpleNamespace(rakuten_app_id='a',rakuten_access_key='k',ebay_client_id='',ebay_client_secret='')
        self.assertEqual(platform_probe.probe('ebay',only_rakuten)['status'],'skipped')
    def test_api_keys_come_from_the_environment_without_building_settings(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ,{'RAKUTEN_APPLICATION_ID':'app','RAKUTEN_ACCESS_KEY':'key','EBAY_CLIENT_ID':'','EBAY_CLIENT_SECRET':''}),patch('config.load_env'):
            keys=platform_probe.api_keys()
        self.assertEqual((keys.rakuten_app_id,keys.rakuten_access_key,keys.ebay_client_id),('app','key',''))
        with patch.dict(os.environ,{'RAKUTEN_APPLICATION_ID':'','EBAY_CLIENT_ID':''}),patch('config.load_env'):
            self.assertIsNone(platform_probe.api_keys())
