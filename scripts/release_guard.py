#!/usr/bin/env python3
"""Local release gate. Never discovers credentials or sends network requests.

An operator supplies a freshly verified, sanitized audit. This is a local
workflow guard, not an account-wide distributed deployment counter.
"""
import argparse
from datetime import datetime, timedelta
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Taipei")
LIMIT = 20
ACCOUNT_LIMIT = 100
ROOT = Path(__file__).resolve().parents[1]

class Blocked(ValueError):
    pass

def instant(value):
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is None:
            raise ValueError()
        return result
    except (TypeError, ValueError):
        raise Blocked("時間證據缺失或無時區") from None

def validate(audit, head, slots, now=None, target="frontend"):
    now = now or datetime.now(TZ)
    if type(slots) is not int or not 0 <= slots <= LIMIT:
        raise Blocked("預留次數必須為 0–20 的整數")
    if not isinstance(audit, dict):
        raise Blocked("缺少發布盤點")
    if audit.get("date") != now.astimezone(TZ).date().isoformat():
        raise Blocked("必須重新盤點台灣今日部署")
    age = now - instant(audit.get("checked_at"))
    if not timedelta(0) <= age <= timedelta(minutes=5):
        raise Blocked("盤點已過期或來自未來；請重新查驗")
    if audit.get("head") != head:
        raise Blocked("盤點對應的 commit 與目前 HEAD 不同")
    counts = []
    account_count = 0
    if target in ("backend", "sync"):
        if slots != 0:
            raise Blocked("後端或純 Git 同步不可消耗 Vercel 次數")
        if target == "sync" and audit.get("automatic_deployments_disabled") is not True:
            raise Blocked("純同步須確認 Git 自動部署已停用")
    else:
        # Unknown, partial, or failed attempts must never be treated as zero.
        if audit.get("scope") != "simples_vercel":
            raise Blocked("Missing SIMPLES Vercel-only deployment scope")
        counts = []
        for key in ("vercel",):
            entry = audit.get(key)
            if not isinstance(entry, dict) or entry.get("complete") is not True:
                raise Blocked("部署紀錄不完整：" + key)
            count = entry.get("count")
            if type(count) is not int or count < 0 or not entry.get("evidence"):
                raise Blocked("缺少有效部署次數或證據：" + key)
            counts.append(count)
        account = audit.get("account")
        if not isinstance(account, dict) or account.get("complete") is not True:
            raise Blocked("Account deployment audit is incomplete")
        account_count = account.get("count")
        if type(account_count) is not int or account_count < sum(counts) or not account.get("evidence"):
            raise Blocked("Invalid account deployment count or evidence")
        if audit.get("automatic_deployments_disabled") is not True:
            raise Blocked("尚未確認 Git／預覽自動部署已停用")
        if audit.get("exclusive_release_window") is not True:
            raise Blocked("尚未確認其他發布者暫停；不可共用過期額度")
    if audit.get("tests_passed") is not True:
        raise Blocked("本批測試尚未完成")
    state = audit.get("api")
    if not isinstance(state, dict) or state.get("verified") is not True:
        raise Blocked("正式 /api/state 尚未驗證")
    if set(("active", "jobs_checked", "schedule_checked", "source_queue_checked")) - state.keys():
        raise Blocked("正式狀態證據不完整")
    if state["active"] is not None or any(state[k] is not True for k in ("jobs_checked", "schedule_checked", "source_queue_checked")):
        raise Blocked("正式工作執行中或狀態未核對")
    if not timedelta(0) <= now - instant(state.get("checked_at")) <= timedelta(minutes=2):
        raise Blocked("正式 API 狀態已過期")
    if instant(state.get("next_run")) - now <= timedelta(minutes=15):
        raise Blocked("已接近或錯過自然排程時段，暫緩發布")
    reserved = audit.get("reservations", [])
    if not isinstance(reserved, list):
        raise Blocked("預留紀錄格式錯誤")
    for r in reserved:
        if not isinstance(r, dict) or type(r.get("slots")) is not int or r["slots"] < 0:
            raise Blocked("預留紀錄格式錯誤")
    reserved_slots = 0 if target == "backend" else sum(r["slots"] for r in reserved if r.get("target") != "backend")
    total = sum(counts) + reserved_slots
    account_total = account_count + reserved_slots
    if total + slots > LIMIT:
        raise Blocked("今日 SIMPLES Vercel 部署將超過 20 次")
    if account_total + slots > ACCOUNT_LIMIT:
        raise Blocked("Account deployments would exceed 100 per day")
    if target in ("backend", "sync"):
        return {"planned":0,"quota_applicable":False}
    return {"used_or_reserved": total, "planned": slots, "remaining_after": LIMIT-total-slots,
            "account_used_or_reserved": account_total,
            "account_remaining_after": ACCOUNT_LIMIT-account_total-slots}

def reserve(path, head, slots, target, now=None):
    # Serialize all releases using the same audit file. Persist before starting
    # the command; a crash, timeout or failed deploy does not refund its slot.
    with open(path, "r+", encoding="utf-8") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        audit = json.load(stream)
        result = validate(audit, head, slots, now, target=target)
        audit.setdefault("reservations", []).append({
            "id": str(uuid.uuid4()), "slots": slots, "target": target,
            "at": (now or datetime.now(TZ)).isoformat(),
        })
        stream.seek(0)
        json.dump(audit, stream, ensure_ascii=False, indent=2)
        stream.truncate()
        stream.flush()
        os.fsync(stream.fileno())
        return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, default=ROOT/"secrets"/"release-audit.json")
    parser.add_argument("--target", choices=("sync", "frontend", "preview", "backend"), required=True)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command[:1] == ["--"]:
        command = command[1:]
    slots = 0 if args.target in ("sync", "backend") else 1
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True):
            raise Blocked("請先完成本機提交，不能發布未提交修改")
        if args.check:
            result = validate(json.loads(args.audit.read_text()), head, slots, target=args.target)
        else:
            if not command:
                raise Blocked("未提供發布命令；不會預留或執行")
            if args.target == "sync" and command != ["git", "push", "origin", "HEAD:main"]:
                raise Blocked("零次數同步只允許 git push origin HEAD:main")
            result = reserve(args.audit, head, slots, args.target)
        print(json.dumps(result, ensure_ascii=False))
        if not args.check:
            env = dict(os.environ, SIMPLES_RELEASE_GUARDED="1")
            return subprocess.run(command, cwd=ROOT, env=env, check=False).returncode
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        # Do not expose raw audit content, commands, or upstream payloads.
        print("發布已阻擋：" + (str(error) if isinstance(error, Blocked) else "缺少可驗證盤點或執行失敗"), file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())
