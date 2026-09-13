import json,tempfile,unittest
from pathlib import Path
from config import Settings
from db import init,connect
import platforms,source_details,source_refresh

def product(platform='tower',eid='123',title='Album',stock='backOrder',end=None,fmt='CD'):
    url=source_details.detail_url(platform,eid)
    offer={'priceCurrency':'JPY','price':5790,'availability':'https://schema.org/'+stock}
    if end:offer['priceValidUntil']=end
    data={'@type':'Product','url':url,'itemId':eid,'itemVariant':fmt,'name':title,'offers':offer}
    return '<script type="application/ld+json">'+json.dumps(data)+'</script>'

class DetailTests(unittest.TestCase):
    def test_tower_backorder_and_stock(self):
        self.assertEqual(source_details.parse('tower','123',product())['availability'],'お取り寄せ')
        self.assertEqual(source_details.parse('tower','123',product(stock='InStock'))['price'],'5790')
    def test_wrong_identity_currency_and_invalid_price_fail(self):
        for raw in [product(eid='124'),product().replace('JPY','USD'),product().replace('5790','0'),product()+product(),'<html>captcha</html>']:
            with self.assertRaises((ValueError,KeyError)):source_details.parse('tower','123',raw)
        with self.assertRaises(ValueError):source_details.detail_url('tower','../123')
    def test_japan_offer_is_never_promoted_to_buy_now_stock(self):
        r=source_details.parse('yahoo_jp','abc',product('yahoo_jp','abc',stock='InStock',end='2099-01-01T00:00:00+09:00'))
        self.assertEqual((r['price_kind'],r['availability']),('current_bid','拍賣中／需確認結標'))
        r=source_details.parse('yahoo_jp','abc',product('yahoo_jp','abc',end='2020-01-01T00:00:00+09:00'))
        self.assertIn('無現貨',r['availability'])
    def test_taiwan_unknown_supply_range_and_unrecognized_state(self):
        data={'item':{'id':'123','type':1,'status':2,'title':'Album','price':500,'totalQuantity':1,'bidInfo':{},'priceRange':{'lowPrice':500,'highPrice':600}}}
        def html():return '<script id="isoredux-data">'+json.dumps(data)+'</script>'
        r=source_details.parse('yahoo_tw','123',html());self.assertEqual((r['price_kind'],r['availability']),('range','未確認'))
        data['item']['totalQuantity']=0;self.assertIn('無現貨',source_details.parse('yahoo_tw','123',html())['availability'])
        data['item']['status']=999
        with self.assertRaises(ValueError):source_details.parse('yahoo_tw','123',html())
    def test_saved_details_bound_retry_identity_and_old_clock(self):
        with tempfile.TemporaryDirectory() as folder:
            s=Settings(db_path=Path(folder)/'test.db');init(s.db_path);platforms.init(s)
            with connect(s.db_path) as c:
                for i in range(1,4):
                    c.execute('INSERT INTO platform_candidates VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(i,'tower',str(i),'test','Album＜初回限定盤＞','Artist','CD','CAT','200','JPY','listed','未確認',source_details.detail_url('tower',str(i)),'2020-01-01T00:00:00+00:00'))
            calls=[]
            def fetch(url):
                eid=url.rsplit('/',1)[-1];calls.append(eid)
                return product(eid=eid,fmt='LP' if eid=='2' else 'CD')+'<h1 class="PC-item-info-title">Album＜初回限定盤＞</h1>'
            report=source_refresh.run(s,fetch,detail_limit=2,sleeper=lambda _:None)
            self.assertEqual((report['attempted'],report['updated'],report['failed']),(2,1,1));self.assertEqual(calls,['1','2']);self.assertEqual(next(p for p in report['platforms'] if p['platform']=='tower')['failures'],[{'external_id':'2','reason':'format_changed'}])
            with connect(s.db_path) as c:
                rows=c.execute('SELECT * FROM platform_candidates ORDER BY id').fetchall()
                self.assertEqual(rows[0]['price'],'5790');self.assertEqual(rows[0]['catalog_no'],'CAT');self.assertTrue(rows[1]['captured_at'].startswith('2020'))
            source_refresh.run(s,fetch,detail_limit=2,sleeper=lambda _:None);self.assertEqual(calls,['1','2','3'])

    def test_diagnostics_are_safe_and_distinguish_identity(self):
        from urllib.error import HTTPError,URLError
        self.assertEqual(source_refresh.failure_reason(HTTPError('https://example.invalid',403,'SECRET',{},None)),'http_403')
        self.assertEqual(source_refresh.failure_reason(URLError('SECRET')),'connection')
        self.assertEqual(source_refresh.failure_reason(ValueError('SECRET')),'unclassified')
        self.assertEqual(source_refresh.failure_reason(ValueError('商品格式變更，待重新配對')),'format_changed')
        self.assertEqual(source_refresh.failure_reason(KeyError('SECRET')),'missing_field')

    def test_direction_marker_is_not_an_edition_change(self):
        self.assertEqual(source_details.text('The Beatles \u200e– Rarities'),source_details.text('The Beatles – Rarities'))
        self.assertNotEqual(source_details.text('Album＜初回限定盤＞'),source_details.text('Album'))

    def test_tower_visible_edition_is_retained_and_conflicts_rejected(self):
        def heading(title):return '<h1 class="is-bold PC-item-info-title">'+title+'</h1>'
        raw=product(title='Album')+heading('Album＜初回限定盤＞')
        self.assertEqual(source_details.parse('tower','123',raw)['title'],'Album＜初回限定盤＞')
        self.assertNotEqual(source_details.parse('tower','123',raw)['title'],'Album＜通常盤＞')
        bundle=product(title='Album')+heading('Album ［SHM-CD+折りポスター］＜限定盤＞')
        self.assertEqual(source_details.parse('tower','123',bundle)['title'],'Album [SHM-CD+折りポスター]＜限定盤＞')
        for extra in [heading('Another Album＜初回限定盤＞'),heading('Album Deluxe'),heading('Album')+heading('Album')]:
            with self.assertRaises(ValueError):source_details.parse('tower','123',product()+extra)

    def test_bundle_brackets_normalize_without_dropping_contents(self):
        self.assertEqual(source_details.text('Album ［LP+Poster］＜限定盤＞'),source_details.text('Album [LP+Poster]＜限定盤＞'))
        self.assertNotEqual(source_details.text('Album ［LP+Poster］'),source_details.text('Album [CD+Poster]'))
