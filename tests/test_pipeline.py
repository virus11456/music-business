import unittest
from unittest.mock import patch
from config import Settings
import pipeline

class PipelineTests(unittest.TestCase):
    def run_cycle(self,source_result,market_error=None):
        with patch('pipeline.DiscogsClient'),patch('pipeline.ingest.fetch_one',side_effect=market_error),patch('pipeline.sourcing.find',return_value=source_result),patch('pipeline.analyze.run'),patch('pipeline.sheet_sync.sync',return_value={'synced':True}) as sync:
            result=pipeline.run(Settings(),[1],['tower'])
            sync.assert_called_once()
            return result
    def test_partial_platform_failure_still_syncs_and_is_reported(self):
        result=self.run_cycle({'failed_platforms':1})
        self.assertEqual(result['failed'],1)
        self.assertTrue(result['sheet_sync']['synced'])
    def test_market_failure_does_not_skip_sources_or_sheet(self):
        result=self.run_cycle({'candidates':2,'failed_platforms':0},RuntimeError('private details'))
        self.assertEqual(result['failed'],1)
        self.assertNotIn('private details',str(result))
        self.assertEqual(result['releases'][0]['sourcing']['candidates'],2)
