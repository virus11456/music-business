import unittest
from datetime import datetime,timezone
from fx import business_day

class BusinessDayTests(unittest.TestCase):
 def test_taipei_midnight_uses_new_day(self):
  self.assertEqual(business_day(datetime(2026,9,10,16,0,tzinfo=timezone.utc)),'2026-09-11')
 def test_before_midnight_remains_previous_day(self):
  self.assertEqual(business_day(datetime(2026,9,10,15,59,tzinfo=timezone.utc)),'2026-09-10')
