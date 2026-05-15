#!/usr/bin/env python3
import json
import os
from pathlib import Path
from typing import Dict, List

import requests


ZABBIX_URL = os.getenv("ZABBIX_URL", "").rstrip("/")
ZABBIX_TOKEN = os.getenv("ZABBIX_API_TOKEN", "").strip()
ZABBIX_HOST = os.getenv("ZABBIX_HOST_NAME", "Hermes-Orchestrator").strip()
STATUS_PATH = Path(os.getenv("ORCHESTRATOR_STATUS_PATH", "/home/sadmin/.hermes/hermes-agent/state/orchestrator_status.json"))


class ZabbixAPI:
    def __init__(self, url: str, token: str):
        if not url or not token:
            raise RuntimeError("ZABBIX_URL and ZABBIX_API_TOKEN are required")
        self.url = f"{url}/api_jsonrpc.php"
        self.token = token
        self._id = 1

    def call(self, method: str, params: Dict):
        body = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self._id,
        }
        self._id += 1
        headers = {"Content-Type": "application/json-rpc", "Authorization": f"Bearer {self.token}"}
        r = requests.post(self.url, json=body, headers=headers, timeout=60)
        r.raise_for_status()
        data = r.json()
        if data.get("error"):
            raise RuntimeError(f"{method} failed: {data['error']}")
        return data.get("result")


def get_host_id(api: ZabbixAPI, host_name: str) -> str:
    res = api.call("host.get", {"filter": {"host": [host_name]}})
    if not res:
        return ""
    return str(res[0]["hostid"])


def get_default_group_id(api: ZabbixAPI) -> str:
    candidates = api.call("hostgroup.get", {"filter": {"name": ["Discovered hosts", "Linux servers", "Templates"]}})
    if candidates:
        return str(candidates[0]["groupid"])
    groups = api.call("hostgroup.get", {"output": ["groupid"], "limit": 1})
    if not groups:
        raise RuntimeError("No host groups available to create host")
    return str(groups[0]["groupid"])


def create_host_if_missing(api: ZabbixAPI, host_name: str) -> str:
    hostid = get_host_id(api, host_name)
    if hostid:
        return hostid
    groupid = get_default_group_id(api)
    created = api.call(
        "host.create",
        {
            "host": host_name,
            "name": host_name,
            "groups": [{"groupid": groupid}],
            "interfaces": [
                {
                    "type": 1,
                    "main": 1,
                    "useip": 1,
                    "ip": "127.0.0.1",
                    "dns": "",
                    "port": "10050",
                }
            ],
            "status": 0,
        },
    )
    return str(created["hostids"][0])


def ensure_item(api: ZabbixAPI, hostid: str, key: str, name: str, value_type: int, units: str = "") -> str:
    found = api.call("item.get", {"hostids": [hostid], "filter": {"key_": [key]}, "output": ["itemid", "value_type", "units"]})
    if found:
        itemid = str(found[0]["itemid"])
        current_vt = int(found[0].get("value_type", value_type)) if str(found[0].get("value_type", "")).isdigit() else value_type
        need_update = current_vt != value_type or str(found[0].get("units") or "") != str(units or "")
        if need_update:
            trends = "0" if value_type in (1, 4) else "90d"
            api.call("item.update", {"itemid": itemid, "value_type": value_type, "trends": trends, "units": units})
        return itemid
    trends = "0" if value_type in (1, 4) else "90d"
    created = api.call(
        "item.create",
        {
            "hostid": hostid,
            "name": name,
            "key_": key,
            "type": 2,
            "value_type": value_type,
            "delay": "0",
            "history": "30d",
            "trends": trends,
            "units": units,
        },
    )
    return str(created["itemids"][0])


def push_item_value(api: ZabbixAPI, itemid: str, value):
    api.call("history.push", [{"itemid": int(itemid), "value": value}])


def ensure_trigger(api: ZabbixAPI, desc: str, expr: str, priority: int):
    found = api.call("trigger.get", {"filter": {"description": [desc]}})
    if found:
        return
    api.call("trigger.create", {"description": desc, "expression": expr, "priority": priority})


def load_status(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    status = load_status(STATUS_PATH)
    api = ZabbixAPI(ZABBIX_URL, ZABBIX_TOKEN)
    hostid = create_host_if_missing(api, ZABBIX_HOST)

    jobs = status.get("jobs", {})
    for job_name, job in jobs.items():
        metrics = job.get("metrics", {})

        status_key = f"hermes.job[{job_name},status]"
        status_item = ensure_item(api, hostid, status_key, f"{job_name}: status", 3)
        push_item_value(api, status_item, int(job.get("status", 2)))

        for mk, mv in metrics.items():
            key = f"hermes.job[{job_name},{mk}]"
            if isinstance(mv, int):
                units = "unixtime" if mk.endswith("_time_s") else ""
                itemid = ensure_item(api, hostid, key, f"{job_name}: {mk}", 3, units=units)
                push_item_value(api, itemid, int(mv))
            elif isinstance(mv, str):
                itemid = ensure_item(api, hostid, key, f"{job_name}: {mk}", 1)
                push_item_value(api, itemid, mv)

        desc_fail = f"Hermes job {job_name} FAIL"
        expr_fail = f"last(/{ZABBIX_HOST}/{status_key})=2"
        ensure_trigger(api, desc_fail, expr_fail, 4)

        desc_stale = f"Hermes job {job_name} STALE"
        expr_stale = f"last(/{ZABBIX_HOST}/{status_key})=1"
        ensure_trigger(api, desc_stale, expr_stale, 3)

    print(f"Zabbix sync done for host {ZABBIX_HOST}: jobs={len(jobs)}")


if __name__ == "__main__":
    main()
