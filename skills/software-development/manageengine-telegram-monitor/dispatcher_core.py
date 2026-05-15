#!/usr/bin/env python3
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

FSM_PATH_ENV = os.getenv("MANAGEENGINE_FSM_PATH", "").strip()
if FSM_PATH_ENV:
    sys.path.insert(0, FSM_PATH_ENV)
else:
    repo_fsm = Path(__file__).resolve().parents[2] / "manageengine-fsm"
    sys.path.insert(0, str(repo_fsm))
    sys.path.insert(0, "/home/sadmin/.hermes/skills/manageengine-fsm")
from api_wrapper import ManageEngineAPI


CATEGORY_NAMES = {
    "601": "Принтера",
    "602": "ПК/Железо",
    "604": "ПО",
    "605": "Сеть",
    "606": "Почта",
    "607": "Доступ",
    "608": "Телефония",
    "610": "Веб-сайт",
    "611": "Безопасность",
    "612": "Прочее",
    "613": "ERP",
    "614": "IoT",
    "615": "VPN/RDS",
}


def now_iso() -> str:
    return datetime.now().isoformat()


def create_incident(
    source_label: str,
    author_label: str,
    body_text: str,
    requester_id: str,
    category_id: str = "612",
    udf_fields: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    api = ManageEngineAPI()
    subject = (body_text or "Письмо без темы").strip()[:100] or "Письмо без темы"
    result = api.create_request(
        subject=subject,
        description=f"[{source_label}] [{author_label}]: {body_text}",
        requester_id=requester_id,
        category_id=category_id if category_id != "612" else None,
        udf_fields=udf_fields or None,
    )
    status = (result.get("response_status") or {}).get("status")
    if status == "success":
        request_id = str((result.get("request") or {}).get("id", "")).strip()
        return {"ok": "1", "action": "created", "request_id": request_id}
    return {"ok": "0", "action": "error", "request_id": ""}


def update_incident(source_label: str, author_label: str, body_text: str, request_id: str) -> Dict[str, str]:
    api = ManageEngineAPI()
    result = api.add_to_description(request_id, f"[{source_label}] [{author_label}]: {body_text}")
    status = (result.get("response_status") or {}).get("status")
    if status == "success":
        return {"ok": "1", "action": "updated", "request_id": str(request_id)}
    return {"ok": "0", "action": "error", "request_id": str(request_id)}


def build_created_5line(request_id: str, user_label: str, user_id_label: str, subject: str, category_id: str) -> str:
    category_name = CATEGORY_NAMES.get(category_id, "Прочее")
    return (
        f"Заявка №{request_id} создана\n"
        f"👤 Пользователь: {user_label} (ID: {user_id_label})\n"
        f"📝 Тема: {subject[:100]}\n"
        f"🏷 Категория: {category_name} ({category_id})\n"
        f"🆔 UDF поле (IDUserTelegram): {user_id_label}"
    )


def send_telegram_room3(text: str) -> bool:
    token = os.getenv("DISPATCHER_TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("INCIDENTS_ROOM3_CHAT_ID", os.getenv("DISPATCHER_TARGET_CHAT_ID", "")).strip()
    topic_id = os.getenv("INCIDENTS_ROOM3_TOPIC_ID", os.getenv("DISPATCHER_TARGET_TOPIC_ID", "")).strip()
    if not token or not chat_id:
        return False
    try:
        import requests

        payload = {
            "chat_id": int(chat_id) if chat_id.lstrip("-").isdigit() else chat_id,
            "text": text,
        }
        if topic_id and topic_id.isdigit():
            payload["message_thread_id"] = int(topic_id)
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(url, json=payload, timeout=20)
        return bool(resp.ok)
    except Exception:
        return False
