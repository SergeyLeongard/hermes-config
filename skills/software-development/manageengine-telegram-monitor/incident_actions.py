#!/usr/bin/env python3
import json
import logging
import os
from pathlib import Path
from typing import Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from api_wrapper import ManageEngineAPI


log = logging.getLogger("incident_actions")

PILOT_ALLOWED_USERNAMES = {
    x.strip().lower()
    for x in os.getenv("DISPATCHER_TAKE_ALLOWED_USERNAMES", "@sergey_al5,@northmund95").split(",")
    if x.strip()
}

ASSIGNMENT_MAP_PATH = Path(
    os.getenv(
        "DISPATCHER_TAKE_ASSIGNMENT_MAP_PATH",
        "/home/sadmin/.hermes/skills/software-development/manageengine-telegram-monitor/take_assignment_map.json",
    )
)
_TECH_DEFAULT_GROUP_CACHE: Dict[str, str] = {}
SET_IN_WORK_STATUS = str(os.getenv("DISPATCHER_TAKE_SET_IN_WORK_STATUS", "true")).strip().lower() in {"1", "true", "yes", "on"}
IN_WORK_STATUS_ID = str(os.getenv("DISPATCHER_TAKE_IN_WORK_STATUS_ID", "5")).strip()


def _load_assignment_map() -> Dict[str, Dict[str, str]]:
    try:
        data = json.loads(ASSIGNMENT_MAP_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    out: Dict[str, Dict[str, str]] = {}
    for k, v in data.items():
        if not isinstance(v, dict):
            continue
        out[str(k).strip()] = {
            "technician_id": str(v.get("technician_id") or "").strip(),
            "group_id": str(v.get("group_id") or "").strip(),
            "name": str(v.get("name") or "").strip(),
        }
    return out


def take_button_markup(request_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text="Принять в работу", callback_data=f"take:{request_id}")]]
    )


def _append_responsible(base_text: str, name: str, group_name: str = "") -> str:
    text = str(base_text or "")
    marker = "\n\n👨‍💻 Ответственный:"
    pos = text.find(marker)
    if pos >= 0:
        text = text[:pos]
    suffix = f" ({group_name})" if str(group_name or "").strip() else ""
    return f"{text}\n\n👨‍💻 Ответственный: {name}{suffix}"


def _request_diag_fields(req: Dict[str, Any]) -> Dict[str, str]:
    group = req.get("group") or {}
    technician = req.get("technician") or {}
    status = req.get("status") or {}
    return {
        "technician_id": str(technician.get("id") or "").strip(),
        "group_id": str(group.get("id") or "").strip(),
        "status_id": str(status.get("id") or "").strip(),
        "status_name": str(status.get("name") or "").strip(),
    }


def _actor_username(update: Update) -> str:
    u = update.effective_user
    if not u or not u.username:
        return ""
    return f"@{u.username}".lower()


def _assignment_for(update: Update) -> Dict[str, str]:
    u = update.effective_user
    if not u:
        return {}
    mapping = _load_assignment_map()
    return mapping.get(str(u.id), {})


def _default_group_for_technician(api: ManageEngineAPI, technician_id: str) -> str:
    tid = str(technician_id or "").strip()
    if not tid:
        return ""
    if tid in _TECH_DEFAULT_GROUP_CACHE:
        return _TECH_DEFAULT_GROUP_CACHE[tid]
    try:
        resp = api._make_request("GET", f"technicians/{tid}")
        tech = resp.get("technician") or {}
        groups = tech.get("support_group") or tech.get("support_groups") or []
        if isinstance(groups, list) and groups:
            gid = str((groups[0] or {}).get("id") or "").strip()
            _TECH_DEFAULT_GROUP_CACHE[tid] = gid
            return gid
    except Exception:
        pass
    _TECH_DEFAULT_GROUP_CACHE[tid] = ""
    return ""


async def _handle_take_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    q = update.callback_query
    if not q or not q.data or not q.data.startswith("take:"):
        return

    request_id = q.data.split(":", 1)[1].strip()
    actor_id = str(update.effective_user.id) if update.effective_user else ""
    actor_username = _actor_username(update)

    if actor_username not in PILOT_ALLOWED_USERNAMES:
        await q.answer("Недостаточно прав для назначения", show_alert=True)
        log.info("take_action request_id=%s result=forbidden_user tg_user_id=%s tg_username=%s", request_id, actor_id, actor_username)
        return

    assign = _assignment_for(update)
    tech_id = str(assign.get("technician_id") or "").strip()
    group_id = str(assign.get("group_id") or "").strip()
    actor_name = str(assign.get("name") or actor_username or actor_id).strip()
    if not tech_id:
        await q.answer("Нет привязки Telegram к специалисту SDP", show_alert=True)
        log.info("take_action request_id=%s result=mapping_not_found tg_user_id=%s tg_username=%s", request_id, actor_id, actor_username)
        return

    api = ManageEngineAPI()
    if not group_id:
        group_id = _default_group_for_technician(api, tech_id)
    status = api.get_request_status(request_id)
    req = status.get("request") or {}
    if not req:
        await q.answer("Заявка не найдена", show_alert=True)
        log.info("take_action request_id=%s result=request_not_found tg_user_id=%s", request_id, actor_id)
        return

    current_tech = req.get("technician") or {}
    current_group_name = str((req.get("group") or {}).get("name") or "").strip()
    current_tid = str(current_tech.get("id") or "").strip()
    current_tname = str(current_tech.get("name") or "").strip()
    if current_tid:
        if current_tid == tech_id:
            await q.answer("Уже у вас в работе")
            if q.message and q.message.text:
                try:
                    await q.message.edit_text(_append_responsible(q.message.text, actor_name, current_group_name), reply_markup=None)
                except Exception:
                    pass
            log.info("take_action request_id=%s result=already_assigned_self tg_user_id=%s technician_id=%s", request_id, actor_id, tech_id)
            return
        await q.answer(f"Уже принял: {current_tname or current_tid}", show_alert=True)
        if q.message and q.message.text:
            try:
                await q.message.edit_text(_append_responsible(q.message.text, current_tname or current_tid, current_group_name), reply_markup=None)
            except Exception:
                pass
        log.info("take_action request_id=%s result=already_taken tg_user_id=%s current_technician_id=%s", request_id, actor_id, current_tid)
        return

    if group_id:
        grp = api.update_request(request_id, {"group": {"id": group_id}})
        grp_status = (grp.get("response_status") or {}).get("status")
        if grp_status != "success":
            await q.answer("Не удалось назначить. Повторите", show_alert=True)
            log.info("take_action request_id=%s result=sdp_validation_error tg_user_id=%s detail=%s", request_id, actor_id, str(grp)[:300])
            return

    upd = api.update_request(request_id, {"technician": {"id": tech_id}})
    upd_status = (upd.get("response_status") or {}).get("status")
    if upd_status != "success":
        await q.answer("Не удалось назначить. Повторите", show_alert=True)
        log.info("take_action request_id=%s result=sdp_validation_error tg_user_id=%s detail=%s", request_id, actor_id, str(upd)[:300])
        return

    verify = api.get_request_status(request_id).get("request") or {}
    vtech = verify.get("technician") or {}
    vgroup_name = str((verify.get("group") or {}).get("name") or "").strip()
    vtid = str(vtech.get("id") or "").strip()
    vtname = str(vtech.get("name") or actor_name).strip()
    if vtid != tech_id:
        diag = _request_diag_fields(verify)
        if not vtid:
            await q.answer("SDP не применил назначение. Попробуйте позже", show_alert=True)
            log.info(
                "take_action request_id=%s result=assign_not_applied tg_user_id=%s expected_technician_id=%s actual_technician_id=%s status_id=%s status_name=%s group_id=%s",
                request_id,
                actor_id,
                tech_id,
                vtid,
                diag.get("status_id") or "",
                diag.get("status_name") or "",
                diag.get("group_id") or "",
            )
            return
        await q.answer(f"Уже принял: {vtname or vtid}", show_alert=True)
        if q.message and q.message.text:
            try:
                    await q.message.edit_text(_append_responsible(q.message.text, vtname or vtid, vgroup_name), reply_markup=None)
            except Exception:
                pass
        log.info("take_action request_id=%s result=already_taken tg_user_id=%s expected_technician_id=%s actual_technician_id=%s", request_id, actor_id, tech_id, vtid)
        return

    status_result = "skipped"
    if SET_IN_WORK_STATUS:
        st = api.update_request(request_id, {"status": {"id": IN_WORK_STATUS_ID}})
        st_status = (st.get("response_status") or {}).get("status")
        if st_status == "success":
            status_result = "set_by_id"
        else:
            st2 = api.update_request(request_id, {"status": {"name": "В работе"}})
            st2_status = (st2.get("response_status") or {}).get("status")
            if st2_status == "success":
                status_result = "set_by_name"
            else:
                status_result = "failed"
                log.info(
                    "take_action request_id=%s result=status_set_failed tg_user_id=%s status_id=%s detail=%s",
                    request_id,
                    actor_id,
                    IN_WORK_STATUS_ID,
                    str(st2)[:300],
                )

    await q.answer("Взято в работу")
    if q.message and q.message.text:
        try:
            await q.message.edit_text(_append_responsible(q.message.text, vtname or actor_name, vgroup_name), reply_markup=None)
        except Exception:
            log.exception("take_action request_id=%s result=telegram_edit_error", request_id)
    log.info(
        "take_action request_id=%s result=ok_assigned tg_user_id=%s tg_username=%s technician_id=%s group_id=%s status_result=%s assign_path=%s",
        request_id,
        actor_id,
        actor_username,
        tech_id,
        group_id,
        status_result,
        "group_then_technician",
    )


def register_handlers(app: Application) -> None:
    app.add_handler(CallbackQueryHandler(_handle_take_callback, pattern=r"^take:"))
