#!/usr/bin/env python3
import datetime as dt
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import quote_plus

import requests


BASE_URL = os.getenv("MANAGEENGINE_URL", "http://s-sd.shin-line.com").rstrip("/")
API_KEY = os.getenv("MANAGEENGINE_API_KEY", "").strip()

IDENTITY_LOG = Path(
    os.getenv(
        "IDENTITY_SYNC_LOG_PATH",
        "/home/sadmin/.hermes/skills/manageengine-fsm/scripts/identity_auto_sync.log",
    )
)
MAPPING_PATH = Path(
    os.getenv(
        "USER_MAPPING_PATH",
        "/home/sadmin/.hermes/skills/manageengine-fsm/user_mapping.json",
    )
)
MAIL_LOG = Path(
    os.getenv(
        "MAIL_INTAKE_LOG_PATH",
        "/home/sadmin/.hermes/skills/software-development/manageengine-telegram-monitor/logs/mail_intake.log",
    )
)
ROADMAP_LOG = Path(
    os.getenv(
        "ROADMAP_BUILD_LOG_PATH",
        "/home/sadmin/.hermes/skills/manageengine-fsm/scripts/build_roadmap_json.log",
    )
)
KNOWLEDGE_LOG = Path(
    os.getenv(
        "KNOWLEDGE_CURATION_LOG_PATH",
        "/home/sadmin/.hermes/logs/knowledge_curation.log",
    )
)


def _read_last_match(path: Path, pattern: re.Pattern) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    matches = pattern.findall(text)
    if not matches:
        return ""
    return matches[-1] if isinstance(matches[-1], str) else ""


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _status_by_mtime(path: Path, stale_minutes: int) -> Tuple[str, str]:
    if not path.exists():
        return "FAIL", "файл не найден"
    age_sec = int(dt.datetime.now().timestamp() - path.stat().st_mtime)
    age_min = age_sec // 60
    if age_min > stale_minutes:
        return "STALE", f"последнее обновление {age_min} мин назад"
    return "OK", f"обновлялся {age_min} мин назад"


def _requests_yesterday_count() -> int:
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
    resp = requests.get(
        url,
        headers={"Authtoken": API_KEY, "Content-Type": "application/x-www-form-urlencoded"},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    reqs = data.get("requests", []) or []
    yesterday = (dt.datetime.now() - dt.timedelta(days=1)).date()
    count = 0
    for row in reqs:
        ct = row.get("created_time") or {}
        disp = ct.get("display_value") if isinstance(ct, dict) else ""
        if not disp:
            continue
        if yesterday.strftime("%d.%m.%Y") in disp or yesterday.strftime("%Y-%m-%d") in disp:
            count += 1
    return count


def _identity_summary_lines(limit: int = 3) -> List[str]:
    mapping = _load_json(MAPPING_PATH, {})
    identities = mapping.get("identities", []) if isinstance(mapping, dict) else []
    picks: List[str] = []
    for rec in reversed(identities):
        if str(rec.get("source") or "") != "auto-sync":
            continue
        requester_id = str(rec.get("requester_id") or "").strip()
        requester_name = str(rec.get("requester_name") or "").strip()
        tg_username = str(rec.get("telegram_username") or "").strip()
        email = str(rec.get("email") or "").strip()
        if not requester_id or (not tg_username and not email):
            continue
        picks.append(
            f"- requester {requester_id} ({requester_name}) с telegram_username={tg_username or '-'} и email {email or '-'}"
        )
        if len(picks) >= limit:
            break
    return picks


def _identity_coverage_line() -> str:
    mapping = _load_json(MAPPING_PATH, {})
    identities = mapping.get("identities", []) if isinstance(mapping, dict) else []
    by_tg = (mapping.get("mapping", {}).get("by_telegram_user_id", {}) or {}) if isinstance(mapping, dict) else {}
    by_email = (mapping.get("mapping", {}).get("by_email", {}) or {}) if isinstance(mapping, dict) else {}
    with_tg_id = sum(1 for x in identities if str(x.get("telegram_user_id") or "").strip())
    with_email = sum(1 for x in identities if str(x.get("email") or "").strip())
    return (
        f"- Покрытие: identities={len(identities)} with_tg_id={with_tg_id} "
        f"with_email={with_email} by_tg_id={len(by_tg)} by_email={len(by_email)}"
    )


def _dispatcher_kpi_lines() -> List[str]:
    try:
        text = subprocess.check_output(
            [
                "journalctl",
                "--user",
                "-u",
                "hermes-dispatcher.service",
                "--since",
                "24 hours ago",
                "--no-pager",
            ],
            text=True,
            errors="replace",
        )
    except Exception as exc:
        return [f"- KPI недоступны: {str(exc)[:120]}"]

    rx = re.compile(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ INFO dispatcher_bot: "
        r"classification user=(\d+) is_it=([^ ]+) triage=([A-Z_]+) category=(\d+) conf=([0-9.]+)(?: msg_preview=(.*))?"
    )
    rows = []
    for m in rx.finditer(text):
        try:
            ts = dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
        preview = str(m.group(7) or "").strip()
        if preview.startswith("'") and preview.endswith("'"):
            preview = preview[1:-1]
        rows.append(
            {
                "ts": ts,
                "user": m.group(2),
                "triage": m.group(4),
                "cat": m.group(5),
                "conf": float(m.group(6)),
                "preview": preview,
            }
        )

    if not rows:
        return ["- KPI: нет classification-событий за 24ч"]

    last30 = rows[-30:]
    non_it = [r for r in last30 if r["triage"] == "NON_IT"]
    it_rows = [r for r in last30 if r["triage"] == "IT"]
    cat612 = sum(1 for r in it_rows if r["cat"] == "612")
    cat612_pct = (cat612 / len(it_rows) * 100.0) if it_rows else 0.0

    retry = 0
    for i, r in enumerate(last30):
        if r["triage"] != "NON_IT":
            continue
        for n in last30[i + 1 : i + 8]:
            if n["user"] != r["user"]:
                continue
            delta = (n["ts"] - r["ts"]).total_seconds() / 60.0
            if delta < 0:
                continue
            if delta <= 30 and n["triage"] == "IT":
                retry += 1
                break

    retry_rate = (retry / len(non_it) * 100.0) if non_it else 0.0

    lines = [
        f"- KPI(24ч/30 событий): total={len(last30)} IT={len(it_rows)} NON_IT={len(non_it)}",
        f"- NON_IT -> IT retry rate: {retry}/{len(non_it)} ({retry_rate:.1f}%)",
        f"- % category=612 среди IT: {cat612}/{len(it_rows)} ({cat612_pct:.1f}%)",
    ]

    if non_it:
        lines.append("- Последние NON_IT (пользователь + текст):")
        for r in non_it[-5:]:
            preview = r["preview"] or "(нет msg_preview в логе)"
            lines.append(
                f"  user={r['user']} ts={r['ts'].strftime('%Y-%m-%d %H:%M:%S')} "
                f"conf={r['conf']:.2f} text={preview}"
            )

    return lines


def build_report() -> str:
    identity_line = _read_last_match(
        IDENTITY_LOG,
        re.compile(r"^(identity_auto_sync:.*)$", re.MULTILINE),
    )
    if not identity_line:
        identity_line = "identity_auto_sync: нет данных"

    identity_examples = _identity_summary_lines(limit=5)
    knowledge_line = _read_last_match(
        KNOWLEDGE_LOG,
        re.compile(r"^(knowledge_curation:.*)$", re.MULTILINE),
    )
    if not knowledge_line:
        knowledge_line = "knowledge_curation: нет данных"
    try:
        y_count = _requests_yesterday_count()
    except Exception as e:
        y_count = -1
        y_err = str(e)
    else:
        y_err = ""

    mail_status, mail_detail = _status_by_mtime(MAIL_LOG, stale_minutes=10)
    roadmap_status, roadmap_detail = _status_by_mtime(ROADMAP_LOG, stale_minutes=15)
    identity_status, identity_detail = _status_by_mtime(IDENTITY_LOG, stale_minutes=24 * 60 + 120)
    knowledge_status, knowledge_detail = _status_by_mtime(KNOWLEDGE_LOG, stale_minutes=8 * 24 * 60)

    lines = []
    lines.append("Короткая сводка оркестрации")
    lines.append("")
    lines.append("a) Сопоставление пользователей")
    lines.append(identity_line)
    if identity_examples:
        lines.extend(identity_examples)
    else:
        lines.append("- Нет новых подтвержденных связей auto-sync")
    lines.append(_identity_coverage_line())

    lines.append("")
    lines.append("b) База заявок")
    if y_count >= 0:
        lines.append(f"- За вчера создано инцидентов: {y_count}")
    else:
        lines.append(f"- Не удалось посчитать инциденты за вчера: {y_err[:160]}")

    lines.append("")
    lines.append("c) Состояние джоб")
    lines.append(f"- mail_intake: {mail_status} ({mail_detail})")
    lines.append(f"- build_roadmap_json: {roadmap_status} ({roadmap_detail})")
    lines.append(f"- identity_auto_sync: {identity_status} ({identity_detail})")
    lines.append(f"- knowledge_curation: {knowledge_status} ({knowledge_detail})")

    lines.append("")
    lines.append("d) База знаний")
    lines.append(knowledge_line)

    lines.append("")
    lines.append("e) KPI triage")
    lines.extend(_dispatcher_kpi_lines())

    fails = [x for x in [mail_status, roadmap_status, identity_status, knowledge_status] if x != "OK"]
    lines.append("")
    if fails:
        lines.append(f"Итог: есть проблемы ({len(fails)}), нужна проверка по пункту c.")
    else:
        lines.append("Итог: все ключевые джобы в OK.")
    return "\n".join(lines)


def main() -> None:
    print(build_report())


if __name__ == "__main__":
    main()
