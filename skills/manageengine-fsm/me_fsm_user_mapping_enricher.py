#!/usr/bin/env python3
"""Daily auto-enrichment for Telegram user -> requester mapping.

Reads yesterday's requests from ManageEngine, extracts UDF IDUserTelegram
(`udf_sline_301`) and current requester, then updates user_mapping.json.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from urllib.parse import urlencode
from urllib.request import Request, urlopen


UDF_FIELD_NAME = "udf_sline_301"
DEFAULT_BASE_URL = "http://s-sd.shin-line.com"
DEFAULT_SADMIN_REQUESTER_ID = "1011"
ROW_COUNT = 50


@dataclass(frozen=True)
class MappingPair:
    telegram_user_id: str
    requester_id: str
    requester_name: str
    ticket_id: str
    seen_at: str


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_telegram_id(raw_value: Any) -> Optional[str]:
    text = str(raw_value or "").strip()
    if not text:
        return None
    if text.isdigit():
        return text
    match = re.fullmatch(r"@id(\d+)", text.lower())
    return match.group(1) if match else None


def day_bounds_ms(now_utc: datetime, tz_offset_hours: int, target_date: Optional[str]) -> Tuple[int, int]:
    local_tz = timezone(timedelta(hours=tz_offset_hours))
    if target_date:
        year, month, day = [int(x) for x in target_date.split("-")]
        local_start = datetime(year, month, day, tzinfo=local_tz)
    else:
        local_now = now_utc.astimezone(local_tz)
        local_start_today = datetime(local_now.year, local_now.month, local_now.day, tzinfo=local_tz)
        local_start = local_start_today - timedelta(days=1)
    start = local_start.astimezone(timezone.utc)
    end = start + timedelta(days=1)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def load_mapping(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {
            "version": 2,
            "updated_at": iso_now(),
            "fallback_requester": "sadmin",
            "mapping": {"by_telegram_user_id": {}},
            "notes": {},
            "conflicts": [],
        }
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_mapping(path: Path, data: Dict[str, Any]) -> None:
    data["updated_at"] = iso_now()
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def append_log(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(f"[{iso_now()}] {message}\n")


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def get_headers(api_key: str) -> Dict[str, str]:
    return {
        "Authtoken": api_key,
        "Content-Type": "application/x-www-form-urlencoded",
    }


def http_get_json(url: str, headers: Dict[str, str], params: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    final_url = url
    if params:
        final_url = f"{url}?{urlencode(params)}"
    request = Request(final_url, headers=headers, method="GET")
    with urlopen(request, timeout=30) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def fetch_requests_page(base_url: str, headers: Dict[str, str], start_index: int) -> Dict[str, Any]:
    list_info = {"list_info": {"row_count": ROW_COUNT, "start_index": start_index}}
    params = {"input_data": json.dumps(list_info, ensure_ascii=False)}
    return http_get_json(f"{base_url}/api/v3/requests", headers, params=params)


def fetch_request_details(base_url: str, headers: Dict[str, str], request_id: str) -> Dict[str, Any]:
    return http_get_json(f"{base_url}/api/v3/requests/{request_id}", headers).get("request", {})


def is_created_yesterday(req: Dict[str, Any], start_ms: int, end_ms: int) -> bool:
    created_value = str((req.get("created_time") or {}).get("value", "")).strip()
    if not created_value.isdigit():
        return False
    created_ms = int(created_value)
    return start_ms <= created_ms < end_ms


def collect_yesterday_requests(base_url: str, headers: Dict[str, str], start_ms: int, end_ms: int) -> List[Dict[str, Any]]:
    start_index = 1
    selected: List[Dict[str, Any]] = []
    while True:
        payload = fetch_requests_page(base_url, headers, start_index)
        batch = payload.get("requests", [])
        if not batch:
            break
        selected.extend([r for r in batch if is_created_yesterday(r, start_ms, end_ms)])
        if not payload.get("list_info", {}).get("has_more_rows", False):
            break
        start_index += ROW_COUNT
    return selected


def extract_pair(request_data: Dict[str, Any], ticket_id: str, now_iso: str) -> Optional[MappingPair]:
    udf_fields = request_data.get("udf_fields") or {}
    telegram_raw = udf_fields.get(UDF_FIELD_NAME)
    telegram_user_id = normalize_telegram_id(telegram_raw)
    requester = request_data.get("requester") or {}
    requester_id = str(requester.get("id", "")).strip()
    requester_name = str(requester.get("name", "")).strip()

    if not telegram_user_id or not requester_id:
        return None
    if requester_id == DEFAULT_SADMIN_REQUESTER_ID or requester_name.lower() == "sadmin":
        return None

    return MappingPair(
        telegram_user_id=telegram_user_id,
        requester_id=requester_id,
        requester_name=requester_name,
        ticket_id=ticket_id,
        seen_at=now_iso,
    )


def upsert_mapping(mapping_data: Dict[str, Any], pair: MappingPair, log_path: Path) -> None:
    by_id = mapping_data.setdefault("mapping", {}).setdefault("by_telegram_user_id", {})
    conflicts = mapping_data.setdefault("conflicts", [])
    existing = by_id.get(pair.telegram_user_id)

    if existing is None:
        by_id[pair.telegram_user_id] = {
            "requester_id": pair.requester_id,
            "requester_name": pair.requester_name,
            "last_seen_username": None,
            "updated_at": pair.seen_at,
            "source": "auto_daily_enrichment",
            "last_ticket_id": pair.ticket_id,
        }
        append_log(log_path, f"ADD mapping tg_id={pair.telegram_user_id} -> requester={pair.requester_id} ticket={pair.ticket_id}")
        return

    existing_requester_id = str(existing.get("requester_id", "")).strip()
    if existing_requester_id == pair.requester_id:
        existing["updated_at"] = pair.seen_at
        existing["last_ticket_id"] = pair.ticket_id
        if pair.requester_name:
            existing["requester_name"] = pair.requester_name
        append_log(log_path, f"TOUCH mapping tg_id={pair.telegram_user_id} requester={pair.requester_id} ticket={pair.ticket_id}")
        return

    conflict_entry = {
        "telegram_user_id": pair.telegram_user_id,
        "existing_requester_id": existing_requester_id,
        "existing_requester_name": existing.get("requester_name"),
        "incoming_requester_id": pair.requester_id,
        "incoming_requester_name": pair.requester_name,
        "ticket_id": pair.ticket_id,
        "detected_at": pair.seen_at,
        "status": "open",
    }
    conflicts.append(conflict_entry)
    append_log(
        log_path,
        "CONFLICT tg_id={} existing={} incoming={} ticket={}".format(
            pair.telegram_user_id,
            existing_requester_id,
            pair.requester_id,
            pair.ticket_id,
        ),
    )


def run() -> int:
    load_env_file(Path(os.path.expanduser("~/.hermes/.env")))
    api_key = os.getenv("MANAGEENGINE_API_KEY", "").strip()
    base_url = os.getenv("MANAGEENGINE_URL", DEFAULT_BASE_URL).rstrip("/")
    if base_url.endswith("/api/v3"):
        base_url = base_url[: -len("/api/v3")]

    if not api_key:
        print("ERROR: MANAGEENGINE_API_KEY not set")
        return 1

    base_dir = Path(__file__).resolve().parent
    mapping_path = base_dir / "user_mapping.json"
    log_path = base_dir / "logs" / "mapping_enricher.log"

    now = datetime.now(timezone.utc)
    tz_offset_hours = int(os.getenv("TZ_OFFSET_HOURS", "0").strip() or "0")
    target_date = os.getenv("TARGET_DATE", "").strip() or None
    start_ms, end_ms = day_bounds_ms(now, tz_offset_hours, target_date)
    headers = get_headers(api_key)
    mapping_data = load_mapping(mapping_path)

    try:
        requests_list = collect_yesterday_requests(base_url, headers, start_ms, end_ms)
    except Exception as exc:
        append_log(log_path, f"ERROR fetch list: {exc}")
        print(f"ERROR: fetch list failed: {exc}")
        return 2

    processed = 0
    for req in requests_list:
        ticket_id = str(req.get("id", "")).strip()
        if not ticket_id:
            continue
        try:
            details = fetch_request_details(base_url, headers, ticket_id)
        except Exception as exc:
            append_log(log_path, f"ERROR fetch ticket={ticket_id}: {exc}")
            continue

        pair = extract_pair(details, ticket_id=ticket_id, now_iso=iso_now())
        if pair is None:
            continue
        upsert_mapping(mapping_data, pair, log_path)
        processed += 1

    save_mapping(mapping_path, mapping_data)
    append_log(log_path, f"DONE processed_pairs={processed} requests_scanned={len(requests_list)}")
    print(f"Done. requests_scanned={len(requests_list)} processed_pairs={processed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
