#!/usr/bin/env python3
"""
Telegram incident monitor logic.
AI classifier provides IT decision and category.
This module handles anti-merge context routing and SDP create/update.
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, "/home/sadmin/.hermes/skills/manageengine-fsm")
from api_wrapper import ManageEngineAPI
from dispatcher_core import create_incident, update_incident


GROUP_CHAT_ID = "-1003990457960"
CONTEXT_FILE = "/home/sadmin/.hermes/skills/software-development/manageengine-telegram-monitor/context.json"
IT_HINTS_FILE = os.getenv(
    "IT_HINTS_FILE",
    "/home/sadmin/.hermes/skills/software-development/manageengine-telegram-monitor/it_hints.json",
)
CONTEXT_TIMEOUT_MINUTES = int(os.getenv("CONTEXT_TTL_MINUTES", "60"))
ACTIVE_TICKET_WINDOW_MINUTES = int(os.getenv("ACTIVE_TICKET_WINDOW_MINUTES", "1440"))
MATCH_SCORE_UPDATE = float(os.getenv("MATCH_SCORE_UPDATE", "0.78"))
MATCH_SCORE_CLARIFY = float(os.getenv("MATCH_SCORE_CLARIFY", "0.45"))

BOT_MENTION_ALIASES = ["@hermessds001bot"]
IMAGE_CACHE_DIR = "/home/sadmin/.hermes/image_cache"
IMAGE_ATTACH_WINDOW_SECONDS = 900
IMAGE_ATTACH_MAX_FILES = 5

NEW_TOPIC_PHRASES = [
    "другая проблема",
    "еще один вопрос",
    "ещё один вопрос",
    "кстати еще",
    "кстати ещё",
    "новая заявка",
]

TELEGRAM_SUPPORT_STAFF_IDS = [
    "387861683",
    "@vlupilin007",
]


def is_support_staff(telegram_user_id: str, username: str = None) -> bool:
    if str(telegram_user_id) in TELEGRAM_SUPPORT_STAFF_IDS:
        return True
    if username:
        user_lower = username.lower()
        for staff in TELEGRAM_SUPPORT_STAFF_IDS:
            if isinstance(staff, str) and staff.lower() == user_lower:
                return True
    return False


def is_greeting(text: str) -> bool:
    greetings = ["здравствуйте", "привет", "добрый день", "доброе утро", "добрый вечер", "hi", "hello"]
    text_lower = text.lower().strip()
    return any(g in text_lower for g in greetings) and len(text_lower.split()) <= 3


def strip_bot_mentions(text: str) -> str:
    cleaned = text
    for alias in BOT_MENTION_ALIASES:
        cleaned = re.sub(re.escape(alias), " ", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip()


def load_context() -> Dict[str, Any]:
    try:
        with open(CONTEXT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {"active_contexts": [], "context_timeout_minutes": CONTEXT_TIMEOUT_MINUTES}
            data.setdefault("active_contexts", [])
            return data
    except FileNotFoundError:
        return {"active_contexts": [], "context_timeout_minutes": CONTEXT_TIMEOUT_MINUTES}


def save_context(context: Dict[str, Any]):
    with open(CONTEXT_FILE, "w", encoding="utf-8") as f:
        json.dump(context, f, indent=2, ensure_ascii=False)


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-Zа-яА-Я0-9_+-]{2,}", text.lower())


def _load_it_hints() -> List[str]:
    try:
        with open(IT_HINTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        hints = data.get("hints", []) if isinstance(data, dict) else []
        return [str(x).strip().lower() for x in hints if str(x).strip()]
    except Exception:
        return []


def _extract_system_markers(text: str, hints: List[str]) -> set:
    text_l = text.lower()
    markers = set()
    for h in hints:
        if h in text_l:
            markers.add(h)
    return markers


def _time_factor(last_update_iso: str) -> float:
    try:
        last = datetime.fromisoformat(last_update_iso)
    except Exception:
        return 0.0
    minutes = max(0.0, (datetime.now() - last).total_seconds() / 60.0)
    horizon = max(1.0, float(ACTIVE_TICKET_WINDOW_MINUTES))
    decay = 1.0 - (minutes / horizon)
    return max(0.0, min(1.0, decay))


def _match_score(message_text: str, category_id: str, ctx: Dict[str, Any], hints: List[str]) -> float:
    old = str(ctx.get("last_message_text", ""))
    t1 = set(_tokenize(message_text))
    t2 = set(_tokenize(old))
    if not t1 or not t2:
        text_sim = 0.0
    else:
        text_sim = len(t1 & t2) / max(1, len(t1 | t2))

    m1 = _extract_system_markers(message_text, hints)
    m2 = _extract_system_markers(old, hints)
    marker_sim = 0.0 if not (m1 or m2) else len(m1 & m2) / max(1, len(m1 | m2))

    cat_bonus = 1.0 if str(ctx.get("last_category_id", "")) == str(category_id) else 0.0
    time_sim = _time_factor(str(ctx.get("last_update", "")))

    return (0.45 * text_sim) + (0.30 * marker_sim) + (0.15 * cat_bonus) + (0.10 * time_sim)


def _cleanup_and_get_user_contexts(telegram_user_id: str, context_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    now = datetime.now()
    ttl = timedelta(minutes=ACTIVE_TICKET_WINDOW_MINUTES)
    active = []
    changed = False
    for ctx in context_data.get("active_contexts", []):
        if ctx.get("telegram_user_id") != telegram_user_id:
            continue
        try:
            last_update = datetime.fromisoformat(ctx.get("last_update", ""))
        except Exception:
            changed = True
            continue
        if now - last_update <= ttl:
            active.append(ctx)
        else:
            changed = True
    if changed:
        keep = []
        for ctx in context_data.get("active_contexts", []):
            try:
                last_update = datetime.fromisoformat(ctx.get("last_update", ""))
            except Exception:
                continue
            if now - last_update <= ttl:
                keep.append(ctx)
        context_data["active_contexts"] = keep
        save_context(context_data)
    return active


def _force_new_topic(message_text: str) -> bool:
    text_l = message_text.lower()
    return any(p in text_l for p in NEW_TOPIC_PHRASES)


def _select_context(
    message_text: str,
    category_id: str,
    contexts: List[Dict[str, Any]],
) -> Tuple[str, Optional[Dict[str, Any]], float]:
    if not contexts:
        return "create", None, 0.0
    if _force_new_topic(message_text):
        return "create", None, 0.0

    hints = _load_it_hints()
    scored = [(_match_score(message_text, category_id, ctx, hints), ctx) for ctx in contexts]
    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_ctx = scored[0]

    if best_score >= MATCH_SCORE_UPDATE:
        return "update", best_ctx, best_score
    if best_score >= MATCH_SCORE_CLARIFY:
        return "clarify", best_ctx, best_score
    return "create", None, best_score


def process_message(
    telegram_user_id: str,
    username: str,
    message_text: str,
    category_id_override: Optional[str] = None,
):
    message_text = strip_bot_mentions(message_text)
    if not message_text:
        return None, "ignored_bot_mention"

    if is_support_staff(telegram_user_id, username):
        return None, "ignored_support_staff"

    if is_greeting(message_text):
        return None, "greeting"

    context_data = load_context()
    category_id = category_id_override or "612"
    user_contexts = _cleanup_and_get_user_contexts(telegram_user_id, context_data)
    decision, chosen_ctx, score = _select_context(message_text, category_id, user_contexts)

    def attach_recent_images(api_obj: ManageEngineAPI, request_id: str):
        now_ts = datetime.now().timestamp()
        image_dir = Path(IMAGE_CACHE_DIR)
        if not image_dir.exists():
            return
        candidates = []
        for p in image_dir.glob("img_*"):
            if not p.is_file():
                continue
            if p.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                continue
            age = now_ts - p.stat().st_mtime
            if 0 <= age <= IMAGE_ATTACH_WINDOW_SECONDS:
                candidates.append(p)
        candidates.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        for p in candidates[:IMAGE_ATTACH_MAX_FILES]:
            api_obj.attach_file_to_request(request_id, str(p), note_text="Telegram image")

    if decision == "clarify" and chosen_ctx:
        return chosen_ctx.get("request_id"), f"clarify_needed:{chosen_ctx.get('request_id')}:{score:.3f}"

    if decision == "update" and chosen_ctx:
        request_id = chosen_ctx["request_id"]
        result = update_incident(source_label="telegram", author_label=username, body_text=message_text, request_id=request_id)
        if result.get("ok") == "1":
            api = ManageEngineAPI()
            attach_recent_images(api, request_id)
            chosen_ctx["last_update"] = datetime.now().isoformat()
            chosen_ctx["last_message_text"] = message_text
            chosen_ctx["last_category_id"] = category_id
            save_context(context_data)
            return request_id, "updated"
        return request_id, "error"

    udf_value = username if str(username).startswith("@") else f"@id{telegram_user_id}"
    udf_fields = {"udf_sline_301": udf_value}
    api = ManageEngineAPI()
    requester_id = api.find_user_by_telegram_id(telegram_user_id)

    result = create_incident(
        source_label="telegram",
        author_label=username,
        body_text=message_text,
        requester_id=requester_id,
        category_id=category_id if category_id != "612" else None,
        udf_fields=udf_fields,
    )
    if result.get("ok") == "1":
        request_id = result.get("request_id")
        attach_recent_images(api, request_id)
        context_data["active_contexts"].append(
            {
                "telegram_user_id": telegram_user_id,
                "username": username,
                "request_id": request_id,
                "last_update": datetime.now().isoformat(),
                "last_message_text": message_text,
                "last_category_id": category_id,
                "chat_id": GROUP_CHAT_ID,
            }
        )
        save_context(context_data)
        return request_id, "created"
    return None, "error"
