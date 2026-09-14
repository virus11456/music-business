from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from scripts.release_guard import Blocked, validate, reserve, TZ

NOW = datetime(2026, 9, 14, 1, 0, tzinfo=TZ)
def valid():
    return {
        "scope":"simples_vercel", "account":{"complete":True,"count":40,"evidence":"all account deployments checked"},
        "date":"2026-09-14", "checked_at":NOW.isoformat(), "head":"abc",
        "vercel":{"complete":True,"count":18,"evidence":"all environments and pages checked"},
        "backend":{"complete":True,"count":8,"evidence":"deployment records checked"},
        "automatic_deployments_disabled":True, "project_deployments_idle":True,
        "tests_passed":True,
        "api":{"verified":True,"active":None,"jobs_checked":True,
               "schedule_checked":True,"source_queue_checked":True,
               "checked_at":NOW.isoformat(),"next_run":NOW.replace(hour=10).isoformat()},
        "reservations":[],
    }

class ReleaseGuardTests(unittest.TestCase):
    def test_twentieth_allowed_twenty_first_blocked(self):
        a=valid()
        self.assertEqual(validate(a,"abc",2,NOW)["remaining_after"],0)
        with self.assertRaises(Blocked):validate(a,"abc",3,NOW)

    def test_unknown_counts_and_partial_audit_fail_closed(self):
        for key in ("vercel",):
            for value in (None,False,-1,"0"):
                a=valid();a[key]["count"]=value
                with self.assertRaises(Blocked):validate(a,"abc",1,NOW)
            a=valid();a[key]["complete"]=False
            with self.assertRaises(Blocked):validate(a,"abc",1,NOW)

    def test_stale_future_wrong_head_and_day(self):
        for field,value in (("date","2026-09-13"),("head","other"),
                            ("checked_at",(NOW-timedelta(minutes=6)).isoformat()),
                            ("checked_at",(NOW+timedelta(seconds=1)).isoformat()),
                            ("checked_at","2026-09-14T01:00:00")):
            a=valid();a[field]=value
            with self.assertRaises(Blocked):validate(a,"abc",1,NOW)

    def test_busy_unknown_and_near_schedule(self):
        for field,value in (("active","running"),("verified",False),
                            ("source_queue_checked",False),
                            ("next_run",(NOW+timedelta(minutes=10)).isoformat()),
                            ("checked_at",(NOW-timedelta(minutes=3)).isoformat())):
            a=valid();a["api"][field]=value
            with self.assertRaises(Blocked):validate(a,"abc",1,NOW)
        a=valid();del a["api"]["active"]
        with self.assertRaises(Blocked):validate(a,"abc",1,NOW)

    def test_uncontrolled_auto_deploy_and_other_publishers_block(self):
        for key in ("automatic_deployments_disabled","project_deployments_idle","tests_passed"):
            a=valid();a[key]=False
            with self.assertRaises(Blocked):validate(a,"abc",1,NOW)

    def test_reservation_survives_retry_and_does_not_refund_failure(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"audit.json";p.write_text(json.dumps(valid()))
            reserve(p,"abc",1,"frontend",NOW)
            reserve(p,"abc",1,"frontend",NOW)
            with self.assertRaises(Blocked):reserve(p,"abc",1,"preview",NOW)
            self.assertEqual(len(json.loads(p.read_text())["reservations"]),2)

    def test_sync_uses_no_slot_but_still_requires_evidence(self):
        a=valid();a["vercel"]["count"]=20
        self.assertEqual(validate(a,"abc",0,NOW)["remaining_after"],0)
        a["vercel"]["complete"]=False
        with self.assertRaises(Blocked):validate(a,"abc",0,NOW)

    def test_taipei_day_not_utc_day(self):
        from datetime import timezone
        self.assertEqual(validate(valid(),"abc",1,NOW.astimezone(timezone.utc))["planned"],1)

    def test_concurrent_reservations_cannot_spend_same_slots(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"audit.json";p.write_text(json.dumps(valid()))
            def attempt(_):
                try:reserve(p,"abc",1,"preview",NOW);return True
                except Blocked:return False
            with ThreadPoolExecutor(max_workers=5) as pool:
                self.assertEqual(sum(pool.map(attempt, range(5))),2)

    def test_other_projects_do_not_consume_project_quota(self):
        a=valid();a["account"]["count"]=90
        result=validate(a,"abc",2,NOW)
        self.assertEqual(result["remaining_after"],0)
        self.assertEqual(result["account_remaining_after"],8)

    def test_account_hundredth_allowed_hundred_first_blocked(self):
        a=valid();a["account"]["count"]=99
        self.assertEqual(validate(a,"abc",1,NOW)["account_remaining_after"],0)
        with self.assertRaises(Blocked):validate(a,"abc",2,NOW)

    def test_unknown_scope_or_account_audit_blocks(self):
        a=valid();del a["scope"]
        with self.assertRaises(Blocked):validate(a,"abc",1,NOW)
        for value in [None,False,-1,"99",17]:
            a=valid();a["account"]["count"]=value
            with self.assertRaises(Blocked):validate(a,"abc",1,NOW)
        a=valid();a["account"]["complete"]=False
        with self.assertRaises(Blocked):validate(a,"abc",1,NOW)

    def test_account_last_slot_reserved_once(self):
        from concurrent.futures import ThreadPoolExecutor
        a=valid();a["account"]["count"]=99
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"audit.json";p.write_text(json.dumps(a))
            def attempt(_):
                try:reserve(p,"abc",1,"frontend",NOW);return True
                except Blocked:return False
            with ThreadPoolExecutor(max_workers=4) as pool:
                self.assertEqual(sum(pool.map(attempt,range(4))),1)

    def test_backend_does_not_need_or_consume_vercel_quota(self):
        a=valid()
        for k in ("scope","account","vercel","backend","automatic_deployments_disabled","project_deployments_idle"):
            del a[k]
        self.assertEqual(validate(a,"abc",0,NOW,target="backend")["planned"],0)
        a["api"]["active"]="running"
        with self.assertRaises(Blocked):validate(a,"abc",0,NOW,target="backend")

    def test_old_scope_requires_fresh_vercel_audit(self):
        a=valid();a["scope"]="simples"
        with self.assertRaises(Blocked):validate(a,"abc",1,NOW)

    def test_pure_git_sync_requires_disabled_auto_build_but_not_quota(self):
        a=valid()
        for k in ("account","vercel","backend","scope","project_deployments_idle"):
            del a[k]
        self.assertEqual(validate(a,"abc",0,NOW,target="sync")["quota_applicable"],False)
        a["automatic_deployments_disabled"]=False
        with self.assertRaises(Blocked):validate(a,"abc",0,NOW,target="sync")
