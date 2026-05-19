#!/usr/bin/env python3
import json
import os
from pathlib import Path
from urllib.parse import quote_plus

import requests


def main() -> None:
    staff_path = Path("/home/sadmin/.hermes/skills/software-development/manageengine-telegram-monitor/it_staff.json")
    user_map_path = Path("/home/sadmin/.hermes/skills/manageengine-fsm/user_mapping.json")
    take_map_path = Path("/home/sadmin/.hermes/skills/software-development/manageengine-telegram-monitor/take_assignment_map.json")
    env_path = Path("/home/sadmin/.hermes/.env.dispatcher")

    staff = json.loads(staff_path.read_text(encoding="utf-8")).get("members", [])
    user_map = json.loads(user_map_path.read_text(encoding="utf-8"))

    existing_take = {}
    if take_map_path.exists():
        try:
            existing_take = json.loads(take_map_path.read_text(encoding="utf-8"))
            if not isinstance(existing_take, dict):
                existing_take = {}
        except Exception:
            existing_take = {}

    by_tg = (user_map.get("mapping") or {}).get("by_telegram_user_id") or {}
    identities = user_map.get("identities") or []

    id_by_tg = {}
    for x in identities:
        tg = str(x.get("telegram_user_id") or "").strip()
        rid = str(x.get("requester_id") or "").strip()
        if tg and rid:
            id_by_tg[tg] = rid

    base = os.getenv("MANAGEENGINE_URL", "http://s-sd.shin-line.com").rstrip("/")
    token = os.getenv("MANAGEENGINE_API_KEY")
    headers = {"Authtoken": token, "Content-Type": "application/x-www-form-urlencoded"}

    def norm(s: str) -> str:
        return (
            str(s or "")
            .strip()
            .lower()
            .replace("ё", "е")
            .replace("й", "и")
            .replace(" ", "")
            .replace("-", "")
        )

    technicians = []
    start_index = 1
    row_count = 200
    while True:
        payload = {"list_info": {"start_index": start_index, "row_count": row_count}}
        endpoint = f"{base}/api/v3/technicians?input_data={quote_plus(json.dumps(payload, ensure_ascii=False))}"
        resp = requests.get(endpoint, headers=headers, timeout=30)
        data = resp.json()
        items = data.get("technicians") or []
        if not items:
            break
        technicians.extend(items)
        list_info = data.get("list_info") or {}
        if not list_info.get("has_more_rows"):
            break
        start_index += row_count

    tech_by_name = {}
    for t in technicians:
        n = norm(t.get("name"))
        if not n:
            continue
        tech_by_name.setdefault(n, []).append(str(t.get("id") or "").strip())

    group_cache = {}

    def tech_group_id(tech_id: str) -> str:
        if not tech_id:
            return ""
        if tech_id in group_cache:
            return group_cache[tech_id]
        try:
            r = requests.get(f"{base}/api/v3/technicians/{tech_id}", headers=headers, timeout=20)
            j = r.json()
            tech = j.get("technician") or {}
            groups = tech.get("support_group") or tech.get("support_groups") or []
            if isinstance(groups, list) and groups:
                gid = str((groups[0] or {}).get("id") or "").strip()
                group_cache[tech_id] = gid
                return gid
        except Exception:
            pass
        group_cache[tech_id] = ""
        return ""

    updated = dict(existing_take)
    allowed_usernames = []
    added = []
    skipped = []

    for m in staff:
        tg_id = str(m.get("telegram_user_id") or "").strip()
        if not tg_id:
            continue
        rid = ""
        entry = by_tg.get(tg_id)
        if isinstance(entry, dict):
            rid = str(entry.get("requester_id") or "").strip()
        if not rid:
            rid = id_by_tg.get(tg_id, "")
        if not rid:
            candidates = tech_by_name.get(norm(m.get("name", "")), [])
            candidates = [x for x in candidates if x]
            if len(candidates) == 1:
                rid = candidates[0]
            else:
                skipped.append({"tg_id": tg_id, "name": m.get("name", ""), "reason": "no_requester_mapping"})
                continue

        gid = tech_group_id(rid)
        if not gid:
            skipped.append({"tg_id": tg_id, "name": m.get("name", ""), "reason": "no_support_group"})
            continue

        updated[tg_id] = {
            "name": str(m.get("name") or "").strip(),
            "technician_id": rid,
            "group_id": gid,
        }
        uname = str(m.get("telegram_username") or "").strip().lower()
        if uname.startswith("@"):
            allowed_usernames.append(uname)
        added.append({"tg_id": tg_id, "name": m.get("name", ""), "tech_id": rid, "group_id": gid})

    for u in ["@sergey_al5", "@northmund95", "@sergey_mossunov", "@chursin_s_v"]:
        if u not in allowed_usernames:
            allowed_usernames.append(u)

    allowed_usernames = sorted(set(allowed_usernames))
    take_map_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = env_path.read_text(encoding="utf-8").splitlines()
    key = "DISPATCHER_TAKE_ALLOWED_USERNAMES"
    val = ",".join(allowed_usernames)
    out = []
    found = False
    for ln in lines:
        if ln.startswith(key + "="):
            out.append(f"{key}={val}")
            found = True
        else:
            out.append(ln)
    if not found:
        out.append(f"{key}={val}")
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")

    print(f"added_or_updated={len(added)}")
    print(f"skipped={len(skipped)}")
    print(f"allowed_usernames={len(allowed_usernames)}")
    print("skipped_list=" + json.dumps(skipped, ensure_ascii=False))


if __name__ == "__main__":
    main()
