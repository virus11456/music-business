import json,os,unittest
from pathlib import Path
from unittest.mock import patch
import state_pack

FIXTURE=Path(__file__).resolve().parents[1]/'frontend/tests/fixtures/state-pack.json'

class PackTests(unittest.TestCase):
    def test_round_trip_keeps_values_nulls_missing_keys_and_types(self):
        rows=[{'a':1,'b':None,'c':[1,{'x':'y'}],'d':True},{'a':1.5,'c':[],'d':False,'e':'only here'},{'a':1,'b':'','c':[1,{'x':'y'}],'d':True}]
        packed=state_pack.pack(rows)
        self.assertEqual(state_pack.unpack(packed),rows)
        self.assertEqual(state_pack.unpack(json.loads(json.dumps(packed,ensure_ascii=False))),rows)
        self.assertEqual(packed['c']['b'].get('m'),[1]);self.assertEqual(packed['c']['e']['m'],[0,2])
        self.assertEqual(state_pack.unpack(state_pack.pack([])),[])
    def test_true_and_one_are_not_merged_by_the_dictionary(self):
        rows=[{'v':1},{'v':True},{'v':1.0},{'v':'1'}]*3
        self.assertEqual([type(r['v']) for r in state_pack.unpack(state_pack.pack(rows))],[type(r['v']) for r in rows])
    def test_repeated_values_use_a_dictionary(self):
        rows=[{'status':'待核對','n':i} for i in range(10)]
        packed=state_pack.pack(rows)
        self.assertEqual(packed['c']['status']['d'],['待核對']);self.assertIn('v',packed['c']['n'])
    def test_unknown_version_is_rejected(self):
        with self.assertRaises(ValueError):state_pack.unpack({'version':2,'n':0,'f':[],'c':{}})
    def test_packed_state_does_not_modify_the_cached_state(self):
        state={'records':[],'workflow':{'comparisons':[{'a':1}],'drafts':[]}}
        out=state_pack.packed_state(state)
        self.assertEqual(state['workflow']['comparisons'],[{'a':1}]);self.assertNotIn('comparisons',out['workflow'])
        self.assertEqual(state_pack.unpack(out['workflow']['comparisons_packed']),[{'a':1}])
    def test_frontend_fixture_matches_the_python_encoder(self):
        fixture=json.loads(FIXTURE.read_text())
        self.assertEqual(state_pack.pack(fixture['rows']),fixture['packed'])
        self.assertEqual(state_pack.unpack(fixture['packed']),fixture['rows'])

class PayloadFormatTests(unittest.TestCase):
    def test_compact_payload_is_separate_and_restores_the_same_comparisons(self):
        from tests.test_state_performance import Repository
        from sheet_primary import PrimaryStore
        import sheet_primary
        from config import Settings
        from server import Dashboard
        repo=Repository();store=PrimaryStore(repo)
        with patch.dict(os.environ,{'DATA_BACKEND':'google_sheets','GOOGLE_SPREADSHEET_ID':'x'*30}),patch.object(sheet_primary,'_store',store):
            app=Dashboard(Settings());app.state()
            for public in (True,False):
                plain=app.payload(public,False);compact=app.payload(public,True)
                self.assertNotEqual(plain[0],compact[0])
                a=json.loads(plain[1]);b=json.loads(compact[1])
                self.assertEqual(state_pack.unpack(b['workflow'].pop('comparisons_packed')),a['workflow'].pop('comparisons'))
                self.assertEqual(a,b)
                self.assertEqual(app.payload(public,True)[3]['cache'],'hit')
