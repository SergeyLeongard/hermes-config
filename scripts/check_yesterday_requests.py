#!/usr/bin/env python3
import datetime
import json
import os
from urllib.parse import quote_plus

import requests


def main() -> None:
    base = os.getenv("MANAGEENGINE_URL", "http://s-sd.shin-line.com").rstrip("/")
    key = os.getenv("MANAGEENGINE_API_KEY", "")
    if not key:
        print("missing MANAGEENGINE env")
        return

    headers = {
        "Authtoken": key,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    payload = {
        "list_info": {
            "start_index": 1,
            "row_count": 200,
            "sort_field": "created_time",
            "sort_order": "desc",
        }
    }
    url = f"{base}/api/v3/requests?input_data={quote_plus(json.dumps(payload, ensure_ascii=False))}"
    resp = requests.get(url, headers=headers, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    reqs = data.get("requests", []) or []
    yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).date()
    rows = []

    for x in reqs:
        ct = x.get("created_time") or {}
        disp = ct.get("display_value") if isinstance(ct, dict) else ""
        if not disp:
            continue
        if yesterday.strftime("%d.%m.%Y") not in disp and yesterday.strftime("%Y-%m-%d") not in disp:
            continue

        rid = str(x.get("id", ""))
        subject = str(x.get("subject", ""))
        requester = x.get("requester") or {}
        req_name = str(requester.get("name", "") or "")
        req_id = str(requester.get("id", "") or "")
        udf = x.get("udf_fields") or {}
        u301 = str(udf.get("udf_sline_301", "") or "")
        rows.append((rid, disp, req_id, req_name, u301, subject[:80]))

    print(f"yesterday_date={yesterday.isoformat()} count={len(rows)}")
    for row in rows:
        print("\t".join(row))


if __name__ == "__main__":
    main()
