import io
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch
import analyze
import demo
import ingest
import notify
from cli import main
from config import Settings, money
from db import init, connect, snapshot, now, decide
from discogs_client import DiscogsClient, APIError, parse_stats, parse_release_market
from fx import convert

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.settings=Settings(db_path=Path(self.temp.name)/'test.sqlite3',token='TEST',telegram_token='TEST',telegram_chat='TEST')
        init(self.settings.db_path)
        demo.seed(self.settings)
        self.rid=900000001

    def tearDown(self):
        self.temp.cleanup()

    def latest(self,c,rid=None):
        return c.execute('SELECT * FROM snapshots WHERE release_id=? ORDER BY captured_at DESC LIMIT 1',(rid or self.rid,)).fetchone()

    def allow_delivery(self):
        with connect(self.settings.db_path) as c:
            c.execute("DELETE FROM meta WHERE key='mode'")

    def test_profit_currency_and_fees(self):
        with connect(self.settings.db_path) as c:
            r=analyze.evaluate(c,self.latest(c),self.settings)
        # USD 75 * 32 - JPY 4500 * .22 - 2400*.12 -600 -50
        self.assertEqual(r['net_twd'],'472.00')
        self.assertAlmostEqual(r['margin'],472/2400)
        self.assertEqual(r['drop_7d'],.25)
        self.assertEqual(set(r['rules']),{'UNDERVALUED','HOT_DEMAND','PRICE_DROP'})

    def test_missing_cost_is_not_profit(self):
        with connect(self.settings.db_path) as c:
            r=analyze.evaluate(c,self.latest(c,900000002),self.settings)
        self.assertIsNone(r['net_twd'])
        self.assertEqual(r['parts']['margin'],.5)
        self.assertNotIn('UNDERVALUED',r['rules'])

    def test_no_supply_does_not_trigger(self):
        with connect(self.settings.db_path) as c:
            r=analyze.evaluate(c,self.latest(c,900000004),self.settings)
        self.assertEqual(r['rules'],[])
        self.assertFalse(r['liquidity'])

    def test_missing_fx_blocks_profit(self):
        with connect(self.settings.db_path) as c:
            c.execute('DELETE FROM fx_rates')
            r=analyze.evaluate(c,self.latest(c),self.settings)
        self.assertIsNone(r['net_twd'])
        self.assertNotIn('UNDERVALUED',r['rules'])

    def test_fx_cannot_use_future_rates(self):
        with connect(self.settings.db_path) as c:
            with self.assertRaises(ValueError):
                convert(c,100,'USD','2001-01-01')

    def test_cross_currency_no_false_drop(self):
        with connect(self.settings.db_path) as c:
            s=self.latest(c)
            c.execute('UPDATE snapshots SET currency=? WHERE id=?',('JPY',s['id']))
            r=analyze.evaluate(c,self.latest(c),self.settings)
        self.assertIsNone(r['drop_7d'])

    def test_stale_baseline_not_seven_day(self):
        with connect(self.settings.db_path) as c:
            c.execute('DELETE FROM snapshots WHERE release_id=? AND id!=?',(self.rid,self.latest(c)['id']))
            snapshot(c,self.rid,(datetime.now(timezone.utc)-timedelta(days=25)).isoformat(),100,'USD',2,100,480)
            r=analyze.evaluate(c,self.latest(c),self.settings)
        self.assertIsNone(r['drop_7d'])

    def test_stale_snapshot_no_rules(self):
        with connect(self.settings.db_path) as c:
            r=analyze.evaluate(c,self.latest(c),self.settings,datetime.now(timezone.utc)+timedelta(days=3))
        self.assertEqual(r['rules'],[])

    def test_one_snapshot_per_taipei_day(self):
        with connect(self.settings.db_path) as c:
            snapshot(c,self.rid,'2020-01-01T17:00:00+00:00',50,'USD',1,1,2)
            snapshot(c,self.rid,'2020-01-02T01:00:00+00:00',40,'USD',1,1,2)
            rows=c.execute("SELECT * FROM snapshots WHERE captured_day='2020-01-02' AND release_id=?",(self.rid,)).fetchall()
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['lowest_price'],'40')

    def test_unknown_fields_fail_closed(self):
        with self.assertRaises(APIError):
            parse_stats({'price':25})
        with self.assertRaises(APIError):
            parse_stats({'lowest_price':25,'num_for_sale':2})
        with self.assertRaises(APIError):
            parse_stats({'lowest_price':None,'num_for_sale':-1})

    def test_null_price_valid(self):
        self.assertEqual(parse_stats({'lowest_price':None,'num_for_sale':0}),(None,None,0))

    def test_invalid_money(self):
        for value in ['nan','Infinity','-1','abc']:
            with self.assertRaises(ValueError):
                money(value)

    def test_repeat_analysis_deduplicates_pending(self):
        analyze.run(self.settings)
        analyze.run(self.settings)
        with connect(self.settings.db_path) as c:
            self.assertEqual(c.execute("SELECT count(*) FROM outbox WHERE release_id=? AND status='pending'",(self.rid,)).fetchone()[0],1)

    def test_decision_cancels_pending(self):
        analyze.run(self.settings)
        with connect(self.settings.db_path) as c:
            decide(c,self.rid,'skip')
        analyze.run(self.settings)
        with connect(self.settings.db_path) as c:
            self.assertEqual(c.execute("SELECT count(*) FROM outbox WHERE release_id=? AND status='pending'",(self.rid,)).fetchone()[0],0)

    def test_watch_requires_price_currency(self):
        with connect(self.settings.db_path) as c:
            with self.assertRaises(ValueError):
                decide(c,self.rid,'watch')
            decide(c,self.rid,'watch','50','USD')
            self.assertEqual(c.execute('SELECT target_currency FROM decisions').fetchone()[0],'USD')

    def test_demo_cannot_send(self):
        analyze.run(self.settings)
        with self.assertRaises(ValueError):
            notify.deliver(self.settings,send=True)

    def test_preview_does_not_mark_sent(self):
        analyze.run(self.settings)
        result=notify.deliver(self.settings)
        self.assertTrue(result)
        with connect(self.settings.db_path) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM alerts_sent').fetchone()[0],0)

    def test_delivery_and_dedup(self):
        self.allow_delivery()
        analyze.run(self.settings)
        calls=[]
        def sender(settings,text):
            calls.append(text)
            return 'sent',None
        notify.deliver(self.settings,send=True,sender=sender)
        analyze.run(self.settings)
        notify.deliver(self.settings,send=True,sender=sender)
        self.assertEqual(len(calls),1)
        with connect(self.settings.db_path) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM alerts_sent').fetchone()[0],1)

    def test_ambiguous_send_not_retried(self):
        self.allow_delivery()
        analyze.run(self.settings)
        calls=[]
        def sender(settings,text):
            calls.append(text)
            return 'uncertain','timeout'
        notify.deliver(self.settings,send=True,sender=sender)
        analyze.run(self.settings)
        notify.deliver(self.settings,send=True,sender=sender)
        self.assertEqual(len(calls),1)
        with connect(self.settings.db_path) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM alerts_sent').fetchone()[0],0)

    def test_ingest_continues_after_single_failure(self):
        class Client:
            def get(inner,path,params=None):
                rid=int(path.split('/')[-1])
                if rid==self.rid:
                    raise APIError('test failure')
                if path.startswith('/releases/'):
                    return {'id':rid,'title':'test','community':{'have':10,'want':20}}
                return {'lowest_price':{'value':10,'currency':'USD'},'num_for_sale':1}
        result=ingest.run(self.settings,Client())
        self.assertEqual(result['success'],3)
        self.assertEqual(result['failed'],1)

    def test_market_from_release_skips_stats_call_in_usd(self):
        calls=[]
        class Client:
            def get(inner,path,params=None):
                calls.append(path)
                if path.startswith('/releases/'):
                    return {'id':self.rid,'title':'test','community':{'have':10,'want':20},'lowest_price':12.5,'num_for_sale':3}
                raise AssertionError('stats endpoint should not be called')
        ingest.fetch_one(Client(),self.settings,self.rid)
        self.assertEqual(calls,[f'/releases/{self.rid}'])
        with connect(self.settings.db_path) as c:row=self.latest(c)
        self.assertEqual((row['lowest_price'],row['currency'],row['num_for_sale'],row['have'],row['want']),('12.5','USD',3,10,20))

    def test_market_falls_back_to_stats_when_release_cannot_answer(self):
        from dataclasses import replace
        stats={'lowest_price':{'value':1800,'currency':'JPY'},'num_for_sale':2}
        for settings,release in ((replace(self.settings,currency='JPY'),{'lowest_price':12.5,'num_for_sale':3}),(self.settings,{})):
            calls=[]
            class Client:
                def get(inner,path,params=None):
                    calls.append(path)
                    return {'id':self.rid,'title':'test','community':{'have':1,'want':2},**release} if path.startswith('/releases/') else stats
            ingest.fetch_one(Client(),settings,self.rid)
            self.assertEqual(calls,[f'/releases/{self.rid}',f'/marketplace/stats/{self.rid}'])
            with connect(self.settings.db_path) as c:row=self.latest(c)
            self.assertEqual((row['lowest_price'],row['currency'],row['num_for_sale']),('1800','JPY',2))

    def test_release_market_matches_stats_on_production_samples(self):
        # (release lowest_price, num_for_sale) as read from Discogs on 2026-10-30 for both endpoints.
        for price,supply in ((5.99,20),(11.01,13),(35.99,2),(11.5,6),(12.99,15),(0.67,123),(None,0)):
            stats={'lowest_price':None if price is None else {'value':price,'currency':'USD'},'num_for_sale':supply}
            self.assertEqual(parse_release_market({'lowest_price':price,'num_for_sale':supply},'USD'),parse_stats(stats))

    def test_release_market_parsing(self):
        self.assertEqual(parse_release_market({'lowest_price':None,'num_for_sale':0},'USD'),(None,None,0))
        self.assertIsNone(parse_release_market({'lowest_price':5,'num_for_sale':1},'EUR'))
        for bad in ({'lowest_price':'5','num_for_sale':1},{'lowest_price':True,'num_for_sale':1},{'lowest_price':5,'num_for_sale':-1}):
            with self.assertRaises(APIError):parse_release_market(bad,'USD')

    def test_shared_rate_budget(self):
        clock=[100.0]
        sleep=lambda seconds: clock.__setitem__(0,clock[0]+seconds)
        a=DiscogsClient(self.settings,clock=lambda:clock[0],sleep=sleep)
        b=DiscogsClient(self.settings,clock=lambda:clock[0],sleep=sleep)
        for i in range(61):
            (a if i%2 else b).wait_turn()
        self.assertGreaterEqual(clock[0]-100,65.9)

    def test_429_retries_bounded(self):
        clock=[100.0]
        calls=[]
        def transport(request,timeout):
            calls.append(request)
            raise HTTPError(request.full_url,429,'test',{'Retry-After':'1'},io.BytesIO())
        client=DiscogsClient(self.settings,transport,lambda:clock[0],lambda s:clock.__setitem__(0,clock[0]+s))
        with self.assertRaises(APIError):
            client.get('/releases/1')
        self.assertEqual(len(calls),4)
        self.assertGreaterEqual(clock[0],107)

    def test_low_header_pauses_next_call(self):
        clock=[100.0]
        class Response(io.BytesIO):
            headers={'X-Discogs-Ratelimit-Remaining':'4'}
        client=DiscogsClient(self.settings,lambda *a,**kw:Response(b'{}'),lambda:clock[0],lambda s:clock.__setitem__(0,clock[0]+s))
        client.get('/releases/1')
        client.get('/releases/2')
        self.assertGreaterEqual(clock[0],160)

    def test_demo_refuses_existing_database(self):
        with self.assertRaises(ValueError):
            demo.seed(self.settings)

    def test_cli_decision_persists(self):
        with patch('sys.stdout',new=io.StringIO()):
            code=main(['--db',str(self.settings.db_path),'decide',str(self.rid),'want'])
        self.assertEqual(code,0)
        with connect(self.settings.db_path) as c:
            self.assertEqual(c.execute('SELECT decision FROM decisions').fetchone()[0],'want')

if __name__=='__main__':
    unittest.main()
