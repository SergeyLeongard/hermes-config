#!/usr/bin/env python3
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import quote_plus


sys.path.insert(0, "/home/sadmin/.hermes/skills/manageengine-fsm")
from api_wrapper import ManageEngineAPI


MAPPING_PATH = Path(os.getenv("USER_MAPPING_PATH", "/home/sadmin/.hermes/skills/manageengine-fsm/user_mapping.json"))
STATE_PATH = Path(os.getenv("IDENTITY_SYNC_STATE_PATH", "/home/sadmin/.hermes/skills/manageengine-fsm/identity_sync_state.json"))
MONITOR_LOG_PATH = Path(
    os.getenv(
        "IDENTITY_SYNC_MONITOR_LOG",
        "/home/sadmin/.hermes/skills/software-development/manageengine-telegram-monitor/logs/monitor.log",
    )
)
DISPATCHER_CONTEXT_PATH = Path(
    os.getenv(
        "IDENTITY_SYNC_CONTEXT_PATH",
        "/home/sadmin/.hermes/skills/software-development/manageengine-telegram-monitor/context.json",
    )
)
FALLBACK_REQUESTER_ID = os.getenv("MANAGEENGINE_FALLBACK_REQUESTER_ID", "1011").strip() or "1011"
LOOKBACK_HOURS = int(os.getenv("IDENTITY_SYNC_LOOKBACK_HOURS", "72") or "72")

CREATED_RE = re.compile(r"created_request\s+.*telegram_user_id=(\d+)\s+request_id=(\d+)")
UDF_TG_ID_RE = re.compile(r"@id(\d+)$", re.IGNORECASE)


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_new_created_pairs() -> Tuple[List[Tuple[str, str]], int]:
    state = load_json(STATE_PATH, {"offset": 0})
    offset = int(state.get("offset", 0) or 0)

    if not MONITOR_LOG_PATH.exists():
        return [], offset

    size = MONITOR_LOG_PATH.stat().st_size
    if offset > size:
        offset = 0

    pairs: List[Tuple[str, str]] = []
    with MONITOR_LOG_PATH.open("r", encoding="utf-8", errors="replace") as f:
        f.seek(offset)
        for line in f:
            m = CREATED_RE.search(line)
            if m:
                tg_id, req_id = m.group(1), m.group(2)
                pairs.append((tg_id.strip(), req_id.strip()))
        new_offset = f.tell()

    return pairs, new_offset


def _extract_created_time_ms(request_row: Dict) -> int:
    created = request_row.get("created_time") or {}
    if isinstance(created, dict):
        for key in ("value", "long_value", "epoch_time", "time"):
            value = created.get(key)
            try:
                return int(value)
            except Exception:
                continue
    return 0


def _extract_tg_id_from_udf(request_row: Dict) -> str:
    udf = request_row.get("udf_fields") or {}
    if not isinstance(udf, dict):
        return ""
    raw = str(udf.get("udf_sline_301") or "").strip()
    if not raw:
        return ""
    m = UDF_TG_ID_RE.match(raw)
    return m.group(1).strip() if m else ""


def read_pairs_from_recent_requests(api: ManageEngineAPI) -> Tuple[List[Dict[str, str]], int]:
    now_ms = int(time.time() * 1000)
    lookback_ms = max(1, LOOKBACK_HOURS) * 60 * 60 * 1000
    since_ms = max(0, now_ms - lookback_ms)
    next_since_ms = since_ms
    records: List[Dict[str, str]] = []

    start_index = 1
    row_count = 1000
    max_rows = 4000
    seen_rows = 0

    while seen_rows < max_rows:
        payload = {
            "list_info": {
                "start_index": start_index,
                "row_count": row_count,
                "sort_field": "created_time",
                "sort_order": "desc",
            }
        }
        endpoint = f"requests?input_data={quote_plus(json.dumps(payload, ensure_ascii=False))}"
        page = api._make_request("GET", endpoint)
        rows = page.get("requests", []) or []
        if not rows:
            break

        for row in rows:
            seen_rows += 1
            request_id = str(row.get("id") or "").strip()
            if not request_id:
                continue

            created_ms = _extract_created_time_ms(row)
            if created_ms > next_since_ms:
                next_since_ms = created_ms
            if created_ms and created_ms <= since_ms:
                continue

            full = api.get_request_status(request_id).get("request", {})
            udf = full.get("udf_fields") or {}
            udf_raw = str((udf.get("udf_sline_301") if isinstance(udf, dict) else "") or "").strip()
            tg_id = ""
            m = UDF_TG_ID_RE.match(udf_raw)
            if m:
                tg_id = m.group(1).strip()
            tg_username = udf_raw.lower() if udf_raw.startswith("@") and not tg_id else ""
            email = udf_raw.lower() if "@" in udf_raw and not udf_raw.startswith("@") else ""
            if tg_id or tg_username or email:
                records.append(
                    {
                        "request_id": request_id,
                        "telegram_user_id": tg_id,
                        "telegram_username": tg_username,
                        "email": email,
                    }
                )

        list_info = page.get("list_info", {}) or {}
        if not list_info.get("has_more_rows"):
            break
        start_index += row_count

    return records, next_since_ms


def load_context_indexes() -> Tuple[Dict[str, str], Dict[str, List[str]]]:
    request_to_tg: Dict[str, str] = {}
    username_to_tg: Dict[str, List[str]] = {}
    data = load_json(DISPATCHER_CONTEXT_PATH, {})
    rows = data.get("active_contexts", []) if isinstance(data, dict) else []
    if not isinstance(rows, list):
        return request_to_tg, username_to_tg

    for row in rows:
        if not isinstance(row, dict):
            continue
        tg_id = str(row.get("telegram_user_id") or "").strip()
        if not tg_id:
            continue
        req_id = str(row.get("request_id") or "").strip()
        if req_id and req_id not in request_to_tg:
            request_to_tg[req_id] = tg_id
        uname = str(row.get("username") or "").strip().lower()
        if uname:
            username_to_tg.setdefault(uname, [])
            if tg_id not in username_to_tg[uname]:
                username_to_tg[uname].append(tg_id)
    return request_to_tg, username_to_tg


def upsert_identity_from_record(
    mapping: Dict,
    requester_id: str,
    requester_name: str,
    requester_email: str,
    telegram_user_id: str,
    telegram_username: str,
    email_from_udf: str,
) -> bool:
    if not requester_id or requester_id == FALLBACK_REQUESTER_ID:
        return False

    mapping.setdefault("version", 1)
    mapping.setdefault("mapping", {})
    mapping["mapping"].setdefault("by_telegram_user_id", {})
    mapping["mapping"].setdefault("by_email", {})
    mapping.setdefault("identities", [])

    changed = False
    normalized_tg_id = str(telegram_user_id or "").strip()
    normalized_username = str(telegram_username or "").strip().lower()
    effective_email = str(requester_email or email_from_udf or "").strip().lower()

    existing_tg_entry = mapping["mapping"]["by_telegram_user_id"].get(normalized_tg_id) if normalized_tg_id else None
    tg_conflict = bool(
        normalized_tg_id
        and isinstance(existing_tg_entry, dict)
        and str(existing_tg_entry.get("requester_id") or "").strip()
        and str(existing_tg_entry.get("requester_id") or "").strip() != requester_id
    )

    if normalized_tg_id and not tg_conflict:
        tg_entry = {
            "requester_id": requester_id,
            "requester_name": requester_name,
            "status": "confirmed",
            "source": "auto-sync",
        }
        if mapping["mapping"]["by_telegram_user_id"].get(normalized_tg_id) != tg_entry:
            mapping["mapping"]["by_telegram_user_id"][normalized_tg_id] = tg_entry
            changed = True

    if effective_email:
        em_entry = {
            "requester_id": requester_id,
            "requester_name": requester_name,
            "status": "confirmed",
            "source": "auto-sync",
        }
        if mapping["mapping"]["by_email"].get(effective_email) != em_entry:
            mapping["mapping"]["by_email"][effective_email] = em_entry
            changed = True

    identities = mapping["identities"]
    idx = -1
    for i, rec in enumerate(identities):
        if str(rec.get("requester_id") or "") == requester_id:
            idx = i
            break

    existing_tg_id = ""
    if idx >= 0:
        existing_tg_id = str(identities[idx].get("telegram_user_id") or "").strip()
    merged_tg_id = existing_tg_id
    if normalized_tg_id and not tg_conflict:
        merged_tg_id = normalized_tg_id
    merged_username = normalized_username
    if not merged_username and idx >= 0:
        merged_username = str(identities[idx].get("telegram_username") or "").strip().lower()

    merged = {
        "requester_id": requester_id,
        "requester_name": requester_name,
        "telegram_user_id": merged_tg_id,
        "telegram_username": merged_username,
        "email": effective_email,
        "status": "confirmed",
        "source": "auto-sync",
    }
    if idx >= 0:
        if identities[idx] != merged:
            identities[idx] = merged
            changed = True
    else:
        identities.append(merged)
        changed = True

    return changed


def extract_requester_fields(api: ManageEngineAPI, request_id: str) -> Tuple[str, str, str, str]:
    data = api.get_request_status(request_id)
    req = data.get("request") or {}
    requester = req.get("requester") or {}
    requester_id = str(requester.get("id") or "").strip()
    requester_name = str(requester.get("name") or requester.get("display_name") or "").strip()
    requester_email = str(requester.get("email_id") or requester.get("email") or "").strip().lower()
    requester_username = str(requester.get("username") or "").strip()
    return requester_id, requester_name, requester_email, requester_username


def upsert_identity(mapping: Dict, telegram_user_id: str, requester_id: str, requester_name: str, requester_email: str) -> bool:
    if not requester_id or requester_id == FALLBACK_REQUESTER_ID:
        return False

    mapping.setdefault("version", 1)
    mapping.setdefault("mapping", {})
    mapping["mapping"].setdefault("by_telegram_user_id", {})
    mapping["mapping"].setdefault("by_email", {})
    mapping.setdefault("identities", [])

    changed = False

    existing_tg_entry = mapping["mapping"]["by_telegram_user_id"].get(telegram_user_id)
    tg_conflict = bool(
        isinstance(existing_tg_entry, dict)
        and str(existing_tg_entry.get("requester_id") or "").strip()
        and str(existing_tg_entry.get("requester_id") or "").strip() != requester_id
    )

    if not tg_conflict:
        tg_entry = {
            "requester_id": requester_id,
            "requester_name": requester_name,
            "status": "confirmed",
            "source": "auto-sync",
        }
        if mapping["mapping"]["by_telegram_user_id"].get(telegram_user_id) != tg_entry:
            mapping["mapping"]["by_telegram_user_id"][telegram_user_id] = tg_entry
            changed = True

    if requester_email:
        em_entry = {
            "requester_id": requester_id,
            "requester_name": requester_name,
            "status": "confirmed",
            "source": "auto-sync",
        }
        if mapping["mapping"]["by_email"].get(requester_email) != em_entry:
            mapping["mapping"]["by_email"][requester_email] = em_entry
            changed = True

    identities = mapping["identities"]
    idx = -1
    for i, rec in enumerate(identities):
        if str(rec.get("requester_id") or "") == requester_id:
            idx = i
            break

    normalized_username = str((identities[idx].get("telegram_username") if idx >= 0 else "") or "").strip().lower()
    merged_tg_id = str((identities[idx].get("telegram_user_id") if idx >= 0 else "") or "").strip()
    if not tg_conflict:
        merged_tg_id = telegram_user_id

    merged = {
        "requester_id": requester_id,
        "requester_name": requester_name,
        "telegram_user_id": merged_tg_id,
        "telegram_username": normalized_username,
        "email": requester_email,
        "status": "confirmed",
        "source": "auto-sync",
    }
    if idx >= 0:
        if identities[idx] != merged:
            identities[idx] = merged
            changed = True
    else:
        identities.append(merged)
        changed = True

    return changed


def main() -> None:
    pairs, new_offset = read_new_created_pairs()
    mapping = load_json(
        MAPPING_PATH,
        {"version": 1, "mapping": {"by_telegram_user_id": {}, "by_email": {}}, "identities": []},
    )

    api = ManageEngineAPI()
    request_to_tg, username_to_tg = load_context_indexes()

    request_records: List[Dict[str, str]] = []
    if not pairs:
        request_records, next_since_ms = read_pairs_from_recent_requests(api)
    else:
        state = load_json(STATE_PATH, {"offset": 0})
        next_since_ms = int(state.get("last_created_time_ms", 0) or 0)

    deduped_pairs: List[Tuple[str, str]] = []
    seen = set()
    for tg_id, req_id in pairs:
        key = (str(tg_id).strip(), str(req_id).strip())
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        deduped_pairs.append(key)

    changed = False
    processed = 0
    for tg_id, req_id in deduped_pairs:
        requester_id, requester_name, requester_email, _ = extract_requester_fields(api, req_id)
        if upsert_identity(mapping, tg_id, requester_id, requester_name, requester_email):
            changed = True
        processed += 1

    deduped_records: List[Dict[str, str]] = []
    seen_req = set()
    for rec in request_records:
        req_id = str(rec.get("request_id") or "").strip()
        if not req_id or req_id in seen_req:
            continue
        seen_req.add(req_id)
        deduped_records.append(rec)

    for rec in deduped_records:
        req_id = str(rec.get("request_id") or "").strip()
        rec_tg_id = str(rec.get("telegram_user_id") or "").strip()
        rec_tg_username = str(rec.get("telegram_username") or "").strip().lower()
        if not rec_tg_id and req_id:
            rec_tg_id = request_to_tg.get(req_id, "")
        if not rec_tg_id and rec_tg_username:
            candidates = username_to_tg.get(rec_tg_username, [])
            if len(candidates) == 1:
                rec_tg_id = candidates[0]

        requester_id, requester_name, requester_email, _ = extract_requester_fields(api, req_id)
        if upsert_identity_from_record(
            mapping=mapping,
            requester_id=requester_id,
            requester_name=requester_name,
            requester_email=requester_email,
            telegram_user_id=rec_tg_id,
            telegram_username=rec_tg_username,
            email_from_udf=str(rec.get("email") or ""),
        ):
            changed = True
        processed += 1

    if changed:
        save_json(MAPPING_PATH, mapping)

    state = load_json(STATE_PATH, {"offset": 0})
    state["offset"] = new_offset
    state["last_created_time_ms"] = int(next_since_ms or state.get("last_created_time_ms", 0) or 0)
    save_json(STATE_PATH, state)
    print(
        "identity_auto_sync: "
        f"processed={processed} changed={int(changed)} offset={new_offset} "
        f"last_created_time_ms={state['last_created_time_ms']}"
    )


if __name__ == "__main__":
    main()
