#!/usr/bin/env python3
import email
import imaplib
import json
import os
import re
from dataclasses import dataclass
from email.header import decode_header
from email.message import Message
from email.utils import parseaddr
from pathlib import Path
from typing import Dict, List, Optional

from dispatcher_core import create_incident, send_telegram_room3

import sys

sys.path.insert(0, "/home/sadmin/.hermes/skills/manageengine-fsm")
from api_wrapper import ManageEngineAPI


STATE_FILE = Path(os.getenv("MAIL_INTAKE_STATE_FILE", "/home/sadmin/.hermes/skills/software-development/manageengine-telegram-monitor/mail_thread_links.json"))
MAIL_PROVIDER = os.getenv("MAIL_PROVIDER", "imap").strip().lower() or "imap"
IMAP_HOST = os.getenv("MAIL_IMAP_HOST", "").strip()
IMAP_PORT = int(os.getenv("MAIL_IMAP_PORT", "993"))
IMAP_USER = os.getenv("MAIL_IMAP_USER", "").strip()
IMAP_PASSWORD = os.getenv("MAIL_IMAP_PASSWORD", "").strip()
IMAP_FOLDER = os.getenv("MAIL_IMAP_FOLDER", "INBOX").strip() or "INBOX"
IMAP_SEARCH = os.getenv("MAIL_IMAP_SEARCH", "UNSEEN").strip() or "UNSEEN"
IMAP_STARTTLS = os.getenv("MAIL_IMAP_STARTTLS", "0").strip().lower() in {"1", "true", "yes", "on"}
MAIL_CHANNEL_CATEGORY_ID = os.getenv("MAIL_CHANNEL_CATEGORY_ID", "612").strip() or "612"
MAIL_FALLBACK_REQUESTER_ID = os.getenv("MANAGEENGINE_FALLBACK_REQUESTER_ID", "1011").strip() or "1011"
EWS_URL = os.getenv("MAIL_EWS_URL", "").strip()
EWS_USERNAME = os.getenv("MAIL_EWS_USERNAME", "").strip()
EWS_PASSWORD = os.getenv("MAIL_EWS_PASSWORD", "").strip()
EWS_MAILBOX = os.getenv("MAIL_EWS_MAILBOX", "").strip()
EWS_FOLDER = os.getenv("MAIL_EWS_FOLDER", "inbox").strip().lower() or "inbox"
EWS_LIMIT = int(os.getenv("MAIL_EWS_LIMIT", "50"))

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


@dataclass
class MailEvent:
    message_id: str
    in_reply_to: str
    references: List[str]
    from_email: str
    from_name: str
    subject: str
    body: str


def _decode_header(value: str) -> str:
    if not value:
        return ""
    decoded = []
    for part, charset in decode_header(value):
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded).strip()


def _normalize_message_id(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if raw.startswith("<") and raw.endswith(">"):
        return raw[1:-1].strip().lower()
    return raw.lower()


def _extract_references(value: str) -> List[str]:
    if not value:
        return []
    refs = re.findall(r"<([^>]+)>", value)
    if refs:
        return [x.strip().lower() for x in refs if x.strip()]
    parts = [x.strip().lower() for x in value.split() if x.strip()]
    return [_normalize_message_id(x) for x in parts if x]


def _extract_body(msg: Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            ctype = (part.get_content_type() or "").lower()
            disp = (part.get("Content-Disposition") or "").lower()
            if ctype == "text/plain" and "attachment" not in disp:
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace").strip()
        return ""
    payload = msg.get_payload(decode=True) or b""
    charset = msg.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace").strip()


def _extract_latest_reply_text(body: str) -> str:
    text = (body or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""

    cut_markers = [
        "\nFrom:",
        "\nSent:",
        "\nTo:",
        "\nSubject:",
        "\n-----Original Message-----",
        "\n________________",
        "\nОт:",
        "\nОтправлено:",
        "\nКому:",
        "\nТема:",
    ]

    cut_pos = len(text)
    for marker in cut_markers:
        pos = text.find(marker)
        if pos != -1 and pos < cut_pos:
            cut_pos = pos

    latest = text[:cut_pos].strip()

    cleaned_lines = []
    for line in latest.split("\n"):
        line_strip = line.strip()
        if not line_strip:
            cleaned_lines.append("")
            continue
        if line_strip.startswith(">"):
            continue
        cleaned_lines.append(line.rstrip())

    compact = "\n".join(cleaned_lines).strip()
    return compact or text[:1000].strip()


def _parse_mail(raw_bytes: bytes) -> MailEvent:
    msg = email.message_from_bytes(raw_bytes)
    from_name, from_email = parseaddr(_decode_header(msg.get("From", "")))
    message_id = _normalize_message_id(msg.get("Message-ID", ""))
    in_reply_to = _normalize_message_id(msg.get("In-Reply-To", ""))
    references = _extract_references(_decode_header(msg.get("References", "")))
    subject = _decode_header(msg.get("Subject", "")).strip() or "Письмо без темы"
    body_raw = _extract_body(msg)
    body = _extract_latest_reply_text(body_raw) or "(пустое тело письма)"
    return MailEvent(
        message_id=message_id,
        in_reply_to=in_reply_to,
        references=references,
        from_email=(from_email or "").strip().lower(),
        from_name=(from_name or "").strip() or (from_email or "unknown"),
        subject=subject,
        body=body,
    )


def _load_state() -> Dict:
    if not STATE_FILE.exists():
        return {"processed_message_ids": [], "message_to_request": {}}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"processed_message_ids": [], "message_to_request": {}}
        data.setdefault("processed_message_ids", [])
        data.setdefault("message_to_request", {})
        return data
    except Exception:
        return {"processed_message_ids": [], "message_to_request": {}}


def _save_state(state: Dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _lookup_request_id(state: Dict, event: MailEvent) -> Optional[str]:
    message_map = state.get("message_to_request", {})
    if event.in_reply_to:
        req = message_map.get(event.in_reply_to)
        if req:
            return str(req)
    for ref in reversed(event.references):
        req = message_map.get(ref)
        if req:
            return str(req)
    return None


def _resolve_requester_for_email(sender_email: str) -> str:
    api = ManageEngineAPI()
    requester = api.find_user_by_email(sender_email)
    return str(requester or MAIL_FALLBACK_REQUESTER_ID)


def _append_mail_note(request_id: str, event: MailEvent) -> bool:
    api = ManageEngineAPI()
    author = f"{event.from_name} <{event.from_email}>"
    note_text = f"[mail] [{author}] Subject: {event.subject}\n\n{event.body}"
    note_result = api.add_note(request_id=request_id, note_text=note_text)
    status = (note_result.get("response_status") or {}).get("status")
    if status == "success":
        return True
    fallback = api.add_to_description(request_id, note_text)
    return (fallback.get("response_status") or {}).get("status") == "success"


def _notify_result(action: str, request_id: str, event: MailEvent, detail: str) -> None:
    user_label = event.from_name or event.from_email or "unknown"
    user_id_label = event.from_email or "unknown"
    udf_telegram_label = ""
    category_id = MAIL_CHANNEL_CATEGORY_ID or "612"
    category_name = CATEGORY_NAMES.get(category_id, "Прочее")
    if action == "created":
        message = (
            f"Заявка №{request_id} создана\n"
            f"👤 Пользователь: {user_label} (ID: {user_id_label})\n"
            f"📝 Тема: {event.subject[:100]}\n"
            f"🏷 Категория: {category_name} ({category_id})\n"
            f"🆔 UDF поле (IDUserTelegram): {udf_telegram_label}"
        )
    elif action == "updated":
        message = (
            f"Добавлено к заявке №{request_id}\n"
            f"👤 Пользователь: {user_label} (ID: {user_id_label})\n"
            f"📝 Тема: {event.subject[:100]}\n"
            f"🏷 Категория: {category_name} ({category_id})\n"
            f"🆔 UDF поле (IDUserTelegram): {udf_telegram_label}"
        )
    else:
        message = (
            f"Mail intake: ошибка\n"
            f"Действие: {action}\n"
            f"Заявка: {request_id or '-'}\n"
            f"От: {event.from_email or '-'}\n"
            f"Деталь: {detail[:180]}"
        )
    send_telegram_room3(message)


def process_mail_event(state: Dict, event: MailEvent) -> None:
    if event.message_id and event.message_id in state.get("processed_message_ids", []):
        return

    request_id = _lookup_request_id(state, event)
    author = f"{event.from_name} <{event.from_email}>"
    source_label = "mail"

    if request_id:
        if _append_mail_note(request_id=request_id, event=event):
            if event.message_id:
                state["message_to_request"][event.message_id] = request_id
                state["processed_message_ids"].append(event.message_id)
            _notify_result("updated", request_id, event, "reply-thread mapped")
            return

    requester_id = _resolve_requester_for_email(event.from_email)
    udf_fields = None
    create_text = f"Subject: {event.subject}\n\n{event.body}"
    result = create_incident(
        source_label=source_label,
        author_label=author,
        body_text=create_text,
        requester_id=requester_id,
        category_id=MAIL_CHANNEL_CATEGORY_ID,
        udf_fields=udf_fields,
    )
    if result.get("ok") == "1":
        created_request_id = result.get("request_id", "")
        if event.message_id:
            state["message_to_request"][event.message_id] = created_request_id
            state["processed_message_ids"].append(event.message_id)
        _notify_result("created", created_request_id, event, "new thread")
        return

    if event.message_id:
        state["processed_message_ids"].append(event.message_id)
    _notify_result("error", request_id or "", event, "create/update failed")


def run_once() -> int:
    if MAIL_PROVIDER == "ews":
        return run_once_ews()

    if not IMAP_HOST or not IMAP_USER or not IMAP_PASSWORD:
        raise RuntimeError("MAIL_IMAP_HOST, MAIL_IMAP_USER, MAIL_IMAP_PASSWORD are required")

    state = _load_state()
    if IMAP_STARTTLS:
        mailbox = imaplib.IMAP4(IMAP_HOST, IMAP_PORT)
    else:
        mailbox = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    try:
        if IMAP_STARTTLS:
            mailbox.starttls()
        mailbox.login(IMAP_USER, IMAP_PASSWORD)
        mailbox.select(IMAP_FOLDER)
        typ, data = mailbox.search(None, IMAP_SEARCH)
        if typ != "OK":
            return 0
        message_nums = data[0].split()
        for num in message_nums:
            typ, payload = mailbox.fetch(num, "(RFC822)")
            if typ != "OK" or not payload or not payload[0]:
                continue
            raw_bytes = payload[0][1]
            if not isinstance(raw_bytes, (bytes, bytearray)):
                continue
            event = _parse_mail(bytes(raw_bytes))
            process_mail_event(state, event)
        _save_state(state)
        return len(message_nums)
    finally:
        try:
            mailbox.logout()
        except Exception:
            pass


def _normalize_bracketed_refs(refs_raw: str) -> List[str]:
    return _extract_references(refs_raw or "")


def run_once_ews() -> int:
    if not EWS_URL or not EWS_USERNAME or not EWS_PASSWORD or not EWS_MAILBOX:
        raise RuntimeError("MAIL_EWS_URL, MAIL_EWS_USERNAME, MAIL_EWS_PASSWORD, MAIL_EWS_MAILBOX are required")

    try:
        from exchangelib import (
            Account,
            Configuration,
            Credentials,
            DELEGATE,
            Message,
            Build,
            Version,
            EWSDateTime,
            EWSTimeZone,
        )
        from exchangelib.protocol import BaseProtocol, NoVerifyHTTPAdapter
    except Exception as exc:
        raise RuntimeError("exchangelib is not installed. Install with: pip install exchangelib") from exc

    BaseProtocol.HTTP_ADAPTER_CLS = NoVerifyHTTPAdapter

    creds = Credentials(username=EWS_USERNAME, password=EWS_PASSWORD)
    config = Configuration(service_endpoint=EWS_URL, credentials=creds)
    account = Account(
        primary_smtp_address=EWS_MAILBOX,
        credentials=creds,
        autodiscover=False,
        config=config,
        access_type=DELEGATE,
    )

    folder = account.inbox if EWS_FOLDER == "inbox" else account.root / EWS_FOLDER
    state = _load_state()
    processed = 0

    # Process oldest first so parent message is linked before reply.
    items = folder.filter(is_read=False).order_by("datetime_received")[: max(1, EWS_LIMIT)]
    for item in items:
        if not isinstance(item, Message):
            continue

        internet_id = _normalize_message_id(getattr(item, "message_id", "") or "")
        if internet_id and internet_id in state.get("processed_message_ids", []):
            continue

        author_email = ""
        author_name = ""
        sender = getattr(item, "sender", None)
        if sender and getattr(sender, "email_address", None):
            author_email = str(sender.email_address).strip().lower()
            author_name = str(getattr(sender, "name", "") or "").strip()

        refs_raw = str(getattr(item, "references", "") or "")
        in_reply_to = _normalize_message_id(str(getattr(item, "in_reply_to", "") or ""))
        raw_body_text = str(getattr(item, "text_body", "") or getattr(item, "body", "") or "").strip()
        body_text = _extract_latest_reply_text(raw_body_text)
        subject = str(getattr(item, "subject", "") or "Письмо без темы").strip() or "Письмо без темы"

        event = MailEvent(
            message_id=internet_id,
            in_reply_to=in_reply_to,
            references=_normalize_bracketed_refs(refs_raw),
            from_email=author_email,
            from_name=author_name or author_email or "unknown",
            subject=subject,
            body=body_text or "(пустое тело письма)",
        )

        process_mail_event(state, event)
        processed += 1
        try:
            item.is_read = True
            item.save(update_fields=["is_read"])
        except Exception:
            pass

    _save_state(state)
    return processed


if __name__ == "__main__":
    run_once()
