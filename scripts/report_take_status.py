#!/usr/bin/env python3
import json


staff = json.load(open(r"C:/Users/LEONGA~1.SER/AppData/Local/Temp/opencode/it_staff.remote.json", encoding="utf-8"))["members"]
take = json.load(open(r"C:/Users/LEONGA~1.SER/AppData/Local/Temp/opencode/take_assignment_map.remote.json", encoding="utf-8"))

skip = {
    "205652605": "no_requester_mapping",
    "81453479": "no_support_group",
    "1957240258": "no_requester_mapping",
    "5010902378": "no_requester_mapping",
    "796408223": "no_requester_mapping",
    "674100967": "no_requester_mapping",
    "495392007": "no_requester_mapping",
    "461374895": "no_requester_mapping",
    "453266230": "no_requester_mapping",
    "1212773855": "no_requester_mapping",
    "6208071196": "no_requester_mapping",
    "1035642485": "no_requester_mapping",
    "7682908607": "no_requester_mapping",
    "387861683": "no_requester_mapping",
    "6533944409": "no_requester_mapping",
}

for i, m in enumerate(staff, 1):
    tg = str(m.get("telegram_user_id", ""))
    name = m.get("name", "")
    uname = m.get("telegram_username", "-") or "-"
    rec = take.get(tg)
    if isinstance(rec, dict) and rec.get("technician_id"):
        print(f"{i:02d}. {name} | {tg} | ENABLED | tech={rec.get('technician_id')} group={rec.get('group_id')}")
    else:
        print(f"{i:02d}. {name} | {tg} | SKIPPED | reason={skip.get(tg, 'not_in_take_map')} username={uname}")
