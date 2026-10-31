"""Rakuten Ichiba and eBay Browse: request shape, auth handling, parsing, and the shared search pipeline."""
import io,json,tempfile,unittest
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from urllib.request import Request
from config import Settings
from db import init,connect
import api_sources,platforms

def settings(tmp):
    return Settings(db_path=Path(tmp)/'t.db',rakuten_app_id='APP',rakuten_access_key='RKEY',ebay_client_id='CID',ebay_client_secret='CSECRET')

RAKUTEN={'pageCount':3,'Items':[
    {'itemCode':'recordshop:10001234','itemName':'中古LP カシオペア MINT JAMS ALR-20002 帯付','itemPrice':4800,'itemUrl':'https://item.rakuten.co.jp/recordshop/10001234/','availability':1},
    {'Item':{'itemCode':'cdshop:abc','itemName':'Casiopea Mint Jams CD','itemPrice':1200,'itemUrl':'https://item.rakuten.co.jp/cdshop/abc/','availability':0}},
    {'itemCode':'bad code with space','itemName':'x','itemPrice':1,'itemUrl':'https://item.rakuten.co.jp/x/'},
    {'itemCode':'evil:1','itemName':'x','itemPrice':1,'itemUrl':'https://evil.example/item'}]}
EBAY={'total':95,'itemSummaries':[
    {'itemId':'v1|155512345678|0','legacyItemId':'155512345678','title':'The Beatles Rubber Soul Japan LP AP-8156 OBI','price':{'value':'249.99','currency':'USD'},'buyingOptions':['FIXED_PRICE','BEST_OFFER'],'itemWebUrl':'https://www.ebay.com/itm/155512345678'},
    {'itemId':'v1|266612345678|0','title':'Rubber Soul CD Japan','currentBidPrice':{'value':'31.00','currency':'USD'},'buyingOptions':['AUCTION'],'itemWebUrl':'https://www.ebay.com/itm/266612345678'},
    {'itemId':'v1|1|0','legacyItemId':'1','title':'x','price':{'value':'1','currency':'USD'},'buyingOptions':['FIXED_PRICE'],'itemWebUrl':'http://www.ebay.com/itm/1'}]}

class Response(io.BytesIO):
    def __init__(self,body,url=''):super().__init__(json.dumps(body).encode());self.url=url
    def __enter__(self):return self
    def __exit__(self,*a):self.close()

class ParseTests(unittest.TestCase):
    def test_rakuten_rows_flat_and_wrapped_with_safe_links_only(self):
        rows,more=api_sources.parse('rakuten',json.dumps(RAKUTEN),page=1)
        self.assertEqual([r['external_id'] for r in rows],['recordshop:10001234','cdshop:abc'])
        self.assertEqual((rows[0]['price'],rows[0]['currency'],rows[0]['price_kind'],rows[0]['availability']),('4800','JPY','listed','來源標示有庫存'))
        self.assertEqual(rows[1]['availability'],'缺貨');self.assertTrue(more)
        self.assertFalse(api_sources.parse('rakuten',json.dumps({**RAKUTEN,'pageCount':3}),page=3)[1])
        self.assertEqual(api_sources.parse('rakuten',json.dumps({'Items':[],'pageCount':0}))[0],[])
        for broken in ({'error':'wrong_parameter'},{'count':0},[]):
            with self.assertRaises(ValueError):api_sources.parse('rakuten',json.dumps(broken))
    def test_ebay_fixed_price_and_auction_rows(self):
        rows,more=api_sources.parse('ebay',json.dumps(EBAY),page=1)
        self.assertEqual([r['external_id'] for r in rows],['155512345678','266612345678'])
        self.assertEqual((rows[0]['price'],rows[0]['currency'],rows[0]['price_kind'],rows[0]['source_url']),('249.99','USD','listed','https://www.ebay.com/itm/155512345678'))
        self.assertEqual((rows[1]['price'],rows[1]['price_kind'],rows[1]['availability']),('31.00','current_bid','拍賣中／需確認結標'))
        self.assertTrue(more);self.assertFalse(api_sources.parse('ebay',json.dumps(EBAY),page=3)[1])
        self.assertEqual(api_sources.parse('ebay',json.dumps({'total':0})),([],False))

class RequestTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=settings(self.tmp.name)
        api_sources._token.update(value=None,expires=0,client=None)
    def tearDown(self):self.tmp.cleanup()
    def test_rakuten_key_travels_in_a_header_and_keyword_is_trimmed_by_bytes(self):
        req=api_sources.request(self.s,'rakuten','カシオペア'*40,2)
        query=parse_qs(urlsplit(req.full_url).query)
        self.assertNotIn('RKEY',req.full_url);self.assertEqual(req.get_header('Accesskey'),'RKEY')
        self.assertEqual((query['applicationId'],query['page'],query['formatVersion']),(['APP'],['2'],['2']))
        self.assertLessEqual(len(query['keyword'][0].encode()),128)
        with self.assertRaises(ValueError):api_sources.request(self.s,'rakuten','x',101)
        with self.assertRaises(ValueError):api_sources.request(replace(self.s,rakuten_access_key=''),'rakuten','x')
    def test_ebay_token_is_fetched_once_and_reused_until_near_expiry(self):
        calls=[];clock=[1000.0]
        def opener(req,timeout):
            calls.append(req);return Response({'access_token':f'T{len(calls)}','expires_in':7200})
        self.assertEqual(api_sources.ebay_token(self.s,opener,lambda:clock[0]),'T1')
        clock[0]+=7000;self.assertEqual(api_sources.ebay_token(self.s,opener,lambda:clock[0]),'T1')
        clock[0]+=200;self.assertEqual(api_sources.ebay_token(self.s,opener,lambda:clock[0]),'T2')
        self.assertTrue(calls[0].get_header('Authorization').startswith('Basic '));self.assertNotIn(b'CSECRET',calls[0].data)
        with self.assertRaises(ValueError):api_sources.ebay_token(replace(self.s,ebay_client_secret=''),opener)
        def bad(req,timeout):return Response({'error':'invalid_client'})
        api_sources._token.update(value=None,expires=0)
        with self.assertRaises(ValueError):api_sources.ebay_token(self.s,bad)
    def test_ebay_search_request_is_music_category_us_marketplace(self):
        api_sources._token.update(value='TOKEN',expires=9e18,client='CID')
        req=api_sources.request(self.s,'ebay','Rubber Soul',3)
        query=parse_qs(urlsplit(req.full_url).query)
        self.assertEqual((query['category_ids'],query['offset'],query['limit']),(['11233'],['80'],['40']))
        self.assertEqual((req.get_header('Authorization'),req.get_header('X-ebay-c-marketplace-id')),('Bearer TOKEN','EBAY_US'))

class PipelineTests(unittest.TestCase):
    def test_platform_search_stores_api_rows_and_reports_more_pages(self):
        tmp=tempfile.TemporaryDirectory();s=settings(tmp.name);init(s.db_path);platforms.init(s)
        api_sources._token.update(value='TOKEN',expires=9e18,client='CID')
        seen=[]
        def fetcher(req):
            seen.append(req);self.assertIsInstance(req,Request)
            return json.dumps(RAKUTEN if 'rakuten' in req.full_url else EBAY)
        result=platforms.search(s,'Casiopea Mint Jams',['rakuten','ebay'],fetcher=fetcher,full_page=True)
        self.assertEqual((result['candidates'],result['failed_platforms']),(4,0))
        self.assertEqual([(p['platform'],p['has_more']) for p in result['platforms']],[('rakuten',True),('ebay',True)])
        with connect(s.db_path) as c:
            stored={(r['platform'],r['currency']) for r in c.execute('SELECT platform,currency FROM platform_candidates')}
        self.assertEqual(stored,{('rakuten','JPY'),('ebay','USD')})
        self.assertTrue(all(p['supported'] for p in platforms.CATALOG if p['id'] in ('rakuten','ebay')))
        missing=platforms.search(replace(s,rakuten_app_id=''),'x',['rakuten'],fetcher=fetcher)
        self.assertEqual(missing['failed_platforms'],1)
        tmp.cleanup()

if __name__=='__main__':unittest.main()
