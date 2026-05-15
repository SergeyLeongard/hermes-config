#!/usr/bin/env python3
import datetime as dt
import json
import os
import re
from pathlib import Path
from urllib.parse import quote_plus

import requests


BASE_URL = os.getenv("MANAGEENGINE_URL", "http://s-sd.shin-line.com").rstrip("/")
API_KEY = os.getenv("MANAGEENGINE_API_KEY", "").strip()
OUT_PATH = Path(os.getenv("ORCHESTRATOR_STATUS_PATH", "/home/sadmin/.hermes/hermes-agent/state/orchestrator_status.json"))
MAPPING_PATH = Path(os.getenv("USER_MAPPING_PATH", "/home/sadmin/.hermes/skills/manageengine-fsm/user_mapping.json"))

JOBS = {
    "identity_auto_sync": {
        "log": Path("/home/sadmin/.hermes/skills/manageengine-fsm/scripts/identity_auto_sync.log"),
        "stale_minutes": 26 * 60,
        "pattern": re.compile(
            r"identity_auto_sync:\s+processed=(\d+)\s+changed=(\d+)\s+offset=(\d+)\s+last_created_time_ms=(\d+)"
        ),
        "pattern_legacy": re.compile(r"identity_auto_sync:\s+processed=(\d+)\s+changed=(\d+)\s+offset=(\d+)"),
        "state": Path("/home/sadmin/.hermes/skills/manageengine-fsm/identity_sync_state.json"),
    },
    "mail_intake": {
        "log": Path("/home/sadmin/.hermes/skills/software-development/manageengine-telegram-monitor/logs/mail_intake.log"),
        "stale_minutes": 10,
    },
    "build_roadmap_json": {
        "log": Path("/home/sadmin/.hermes/skills/manageengine-fsm/scripts/build_roadmap_json.log"),
        "stale_minutes": 15,
    },
}


def status_from_log(path: Path, stale_minutes: int):
    if not path.exists():
        return 2, "log missing"
    age_min = int((dt.datetime.now().timestamp() - path.stat().st_mtime) // 60)
    if age_min > stale_minutes:
        return 1, f"stale: {age_min} min"
    return 0, f"ok: {age_min} min"


def parse_identity_metrics(path: Path, pattern: re.Pattern, legacy_pattern: re.Pattern, state_path: Path):
    if not path.exists():
        base = {"processed": 0, "changed": 0, "offset": 0, "last_created_time_ms": 0}
        if state_path.exists():
            try:
                st = json.loads(state_path.read_text(encoding="utf-8"))
                base["last_created_time_ms"] = int(st.get("last_created_time_ms", 0) or 0)
                base["offset"] = int(st.get("offset", 0) or 0)
            except Exception:
                pass
        return base
    text = path.read_text(encoding="utf-8", errors="replace")
    m = pattern.findall(text)
    if m:
        p, c, o, t = m[-1]
        t_int = int(t)
        human = dt.datetime.fromtimestamp(t_int / 1000.0, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") if t_int > 0 else ""
        return {
            "processed": int(p),
            "changed": int(c),
            "offset": int(o),
            "last_created_time_ms": t_int,
            "last_created_time_s": int(t_int // 1000) if t_int > 0 else 0,
            "last_created_time_human": human,
        }

    legacy = legacy_pattern.findall(text)
    if legacy:
        p, c, o = legacy[-1]
        last_created = 0
        if state_path.exists():
            try:
                st = json.loads(state_path.read_text(encoding="utf-8"))
                last_created = int(st.get("last_created_time_ms", 0) or 0)
            except Exception:
                last_created = 0
        human = dt.datetime.fromtimestamp(last_created / 1000.0, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") if last_created > 0 else ""
        return {
            "processed": int(p),
            "changed": int(c),
            "offset": int(o),
            "last_created_time_ms": int(last_created),
            "last_created_time_s": int(last_created // 1000) if last_created > 0 else 0,
            "last_created_time_human": human,
        }

    return {
        "processed": 0,
        "changed": 0,
        "offset": 0,
        "last_created_time_ms": 0,
        "last_created_time_s": 0,
        "last_created_time_human": "",
    }


def identity_coverage_metrics(mapping_path: Path):
    base = {
        "identities_total": 0,
        "identities_auto_sync": 0,
        "with_telegram_user_id": 0,
        "with_telegram_username": 0,
        "with_email": 0,
        "by_telegram_user_id_count": 0,
        "by_email_count": 0,
    }
    if not mapping_path.exists():
        return base
    try:
        data = json.loads(mapping_path.read_text(encoding="utf-8"))
    except Exception:
        return base

    identities = data.get("identities", []) if isinstance(data, dict) else []
    by_tg = (data.get("mapping", {}).get("by_telegram_user_id", {}) or {}) if isinstance(data, dict) else {}
    by_email = (data.get("mapping", {}).get("by_email", {}) or {}) if isinstance(data, dict) else {}

    base["identities_total"] = len(identities)
    base["identities_auto_sync"] = sum(1 for x in identities if str(x.get("source") or "") == "auto-sync")
    base["with_telegram_user_id"] = sum(1 for x in identities if str(x.get("telegram_user_id") or "").strip())
    base["with_telegram_username"] = sum(1 for x in identities if str(x.get("telegram_username") or "").strip())
    base["with_email"] = sum(1 for x in identities if str(x.get("email") or "").strip())
    base["by_telegram_user_id_count"] = len(by_tg)
    base["by_email_count"] = len(by_email)
    return base


def requests_yesterday_count() -> int:
    if not API_KEY:
        return -1
    payload = {
        "list_info": {
            "start_index": 1,
            "row_count": 300,
            "sort_field": "created_time",
            "sort_order": "desc",
        }
    }
    url = f"{BASE_URL}/api/v3/requests?input_data={quote_plus(json.dumps(payload, ensure_ascii=False))}"
    r = requests.get(url, headers={"Authtoken": API_KEY, "Content-Type": "application/x-www-form-urlencoded"}, timeout=60)
    r.raise_for_status()
    rows = (r.json().get("requests") or [])
    y = (dt.datetime.now() - dt.timedelta(days=1)).date()
    count = 0
    for row in rows:
        disp = ((row.get("created_time") or {}).get("display_value") or "")
        if y.strftime("%d.%m.%Y") in disp or y.strftime("%Y-%m-%d") in disp:
            count += 1
    return count


def main():
    jobs = {}
    for job, cfg in JOBS.items():
        status, detail = status_from_log(cfg["log"], cfg["stale_minutes"])
        jobs[job] = {
            "status": status,
            "detail": detail,
            "log_path": str(cfg["log"]),
            "updated_ts": int(cfg["log"].stat().st_mtime) if cfg["log"].exists() else 0,
            "metrics": {},
        }
        if job == "identity_auto_sync":
            jobs[job]["metrics"] = parse_identity_metrics(
                cfg["log"],
                cfg["pattern"],
                cfg["pattern_legacy"],
                cfg["state"],
            )
            jobs[job]["metrics"].update(identity_coverage_metrics(MAPPING_PATH))

    try:
        base_incidents = requests_yesterday_count()
    except Exception as e:
        base_incidents = -1
        jobs["base_incident_count"] = {
            "status": 2,
            "detail": f"api failed: {str(e)[:180]}",
            "log_path": "",
            "updated_ts": int(dt.datetime.now().timestamp()),
            "metrics": {"yesterday_count": -1},
        }
    else:
        jobs["base_incident_count"] = {
            "status": 0,
            "detail": "ok",
            "log_path": "",
            "updated_ts": int(dt.datetime.now().timestamp()),
            "metrics": {"yesterday_count": int(base_incidents)},
        }

    payload = {
        "generated_at": dt.datetime.now().isoformat(),
        "jobs": jobs,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(str(OUT_PATH))


if __name__ == "__main__":
    main()
