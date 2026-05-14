#!/usr/bin/env python3
import json
import re
from pathlib import Path


HEADER_RE = re.compile(r"^##\s+Этап\s+([A-Za-z0-9]+)\s*[—-]\s*(.+)$")
ITEM_RE = re.compile(r"^\d+\.\s+(.+?)\s*(?:-\s*готово)?\s*[;.]?\s*$", re.IGNORECASE)
ITEM_DONE_RE = re.compile(r"-\s*готово\s*[;.]?\s*$", re.IGNORECASE)


def _finalize_stage(stage: dict) -> dict:
    total = stage.pop("_total_items", 0)
    done = stage.pop("_done_items", 0)

    if total > 0:
        raw = (done / total) * 100
        stage["progress"] = int(raw // 10) * 10
    else:
        stage["progress"] = max(0, min(int(stage["progress"]), 100))
    return stage


def parse(md_text: str):
    stages = []
    current = None
    for raw in md_text.splitlines():
        line = raw.strip()
        if not line:
            continue

        m = HEADER_RE.match(line)
        if m:
            if current:
                stages.append(_finalize_stage(current))
            current = {
                "code": m.group(1),
                "title": m.group(2),
                "progress": 0,
                "details": [],
                "_total_items": 0,
                "_done_items": 0,
            }
            continue

        if not current:
            continue

        im = ITEM_RE.match(line)
        if im:
            current["_total_items"] += 1
            if ITEM_DONE_RE.search(line):
                current["_done_items"] += 1
            current["details"].append(im.group(1).strip())

    if current:
        stages.append(_finalize_stage(current))
    return stages


def calculate_overall_progress(stages: list[dict]) -> int:
    total_items = 0
    done_items = 0
    for stage in stages:
        details = stage.get("details") or []
        total_items += len(details)
        progress = int(stage.get("progress", 0))
        done_items += round((progress / 100) * len(details))

    if total_items == 0:
        return 0

    raw = (done_items / total_items) * 100
    return max(0, min(100, int(round(raw))))


def main():
    md_path = Path("/home/sadmin/.hermes/skills/manageengine-fsm/manageengine-telegram-monitor-ROADMAP.md")
    out_path = Path("/home/sadmin/.hermes/skills/manageengine-fsm/roadmap.json")
    text = md_path.read_text(encoding="utf-8")
    stages = parse(text)
    payload = {
        "overall_progress": calculate_overall_progress(stages),
        "stages": stages,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out_path} with {len(stages)} stages")


if __name__ == "__main__":
    main()
