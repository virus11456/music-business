import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch
from config import Settings
from db import init,connect
import platforms

class PlatformTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.s=Settings(db_path=Path(self.temp.name)/'test.db');init(self.s.db_path);platforms.init(self.s)
 def tearDown(self):self.temp.cleanup()
 def yahoo(self,title='Test record'):
  return '<script id="isoredux-data">'+json.dumps({'search':{'ecsearch':{'hits':[{'ec_productid':'123','ec_title':title,'ec_price':'600','pres_data':{'currency':'TWD'},'ec_min_price':'500','ec_max_price':'800'}]}}})+'</script>'
 def test_range_not_fixed_and_no_grading_guessed(self):
  r=platforms.parse_yahoo_tw(self.yahoo())[0];self.assertEqual(r['price_kind'],'range');self.assertEqual(r['format'],'未確認')
 def test_auction_is_not_buy_now_cost(self):
  r=platforms.parse_yahoo_jp('<li class="Product"><a data-auction-id="a123" data-auction-price="99" data-auction-title="Record"></a></li>')[0]
  self.assertEqual(r['price_kind'],'current_bid');self.assertEqual(r['currency'],'JPY')
 def test_missing_markup_fails_visibly(self):
  for parser in platforms.PARSERS.values():
   with self.assertRaises((ValueError,KeyError)):parser('<html>please login</html>')
 def test_price_is_finite_positive(self):
  for p in ['NaN','Infinity','-1','0','unknown']:self.assertIsNone(platforms.price(p))
  self.assertEqual(platforms.price('1,980'),'1980')
 def test_search_upserts_without_fake_offer(self):
  with patch('platforms.time.sleep'):
   platforms.search(self.s,'test',['yahoo_tw'],lambda _:self.yahoo())
   platforms.search(self.s,'test',['yahoo_tw'],lambda _:self.yahoo('Updated'))
  rows=platforms.state(self.s)['candidates'];self.assertEqual(len(rows),1);self.assertEqual(rows[0]['title'],'Updated')
 def test_platform_failure_isolated(self):
  def fetch(url):
   if 'auctions.yahoo.co.jp' in url:raise HTTPError(url,403,'blocked',{},None)
   return self.yahoo()
  result=platforms.search(self.s,'test',['yahoo_jp','yahoo_tw'],fetch)
  self.assertEqual(result,{'candidates':1,'failed_platforms':1,'platforms':[{'platform':'yahoo_jp','count':0,'status':'failed'},{'platform':'yahoo_tw','count':1,'status':'success'}]})
  self.assertIn('403',platforms.state(self.s)['runs'][1]['status'])
 def test_query_is_encoded_not_url_injected(self):
  self.assertEqual(platforms.search_url('tower','a/b?x=1'),'https://tower.jp/search/item/a%2Fb%3Fx%3D1')
 def test_tower_filters_goods_and_preserves_preorder(self):
  def item(fmt):return f'<div class="TOL-item-search-result-PC-result-list-display-item"><span class="result-display-contents-category-text">{fmt}</span><a class="tr-item-block" href="https://tower.jp/item/123"></a><div class="tr-item-block-info-item-name"><a>Test</a></div><span class="is-text-amount">&yen;1,980</span>予約受付中 規格品番： ABC-1 |</div>'
  r=platforms.parse_tower(item('SHM-CD')+item('カレンダー'));self.assertEqual(len(r),1);self.assertEqual(r[0]['availability'],'予約受付中');self.assertEqual(r[0]['price'],'1980');self.assertEqual(r[0]['catalog_no'],'ABC-1')

 def test_ruten_currency_range_stock(self):
  rows=platforms.parse_ruten(json.dumps([{'ProdId':'123','ProdName':'CD','Currency':'TWD','PriceRange':[200,400],'SaleType':'buy','StockStatus':2}]))
  self.assertEqual(rows[0]['price_kind'],'range');self.assertEqual(rows[0]['availability'],'預購')
 def test_ruten_two_stage_search(self):
  calls=[]
  def fetch(url):
   calls.append(url)
   if '/search/' in url:return json.dumps({'Rows':[{'Id':'123'}]})
   return json.dumps([{'ProdId':'123','ProdName':'CD','Currency':'TWD','PriceRange':[200,200],'SaleType':'buy','StockStatus':1}])
  with patch('platforms.time.sleep'):
   result=platforms.search(self.s,'Beatles',['ruten'],fetch)
  self.assertEqual(result['candidates'],1);self.assertEqual(len(calls),2)

 def test_tower_page_url_and_product_pager(self):
  self.assertTrue(platforms.search_url('tower','The Beatles',2).endswith('?page=2'))
  modal='querySelector(".common-pagination-modal.artist-name"); const totalPages = Math.ceil(999 / 10)'
  product='querySelector(".common-pagination"); const totalPages = Math.ceil(25 / 24)'
  self.assertIsNone(platforms.tower_pages(modal))
  self.assertEqual(platforms.tower_pages(modal+product),2)
 def test_tower_non_music_page_keeps_pagination(self):
  html='<div class="TOL-item-search-result-PC-result-list-display-item"><span class="result-display-contents-category-text">カレンダー</span></div><script>querySelector(".common-pagination"); const totalPages = Math.ceil(49 / 24)</script>'
  report=platforms.search(self.s,'test',['tower'],lambda _:html,full_page=True)
  self.assertEqual(report['candidates'],0)
  self.assertTrue(report['platforms'][0]['has_more'])
  with patch('platforms.time.sleep'):
   report=platforms.search(self.s,'test',['tower'],lambda _:html,page=3,full_page=True)
  self.assertFalse(report['platforms'][0]['has_more'])
 def test_tower_zero_results_and_unknown_pager(self):
  empty='<script>querySelector(".common-pagination"); const totalPages = Math.ceil(0 / 24)</script>'
  self.assertEqual(platforms.parse_tower(empty),[])
  report=platforms.search(self.s,'test',['tower'],lambda _:'検索結果 0',full_page=True)
  self.assertEqual(report['failed_platforms'],1)
