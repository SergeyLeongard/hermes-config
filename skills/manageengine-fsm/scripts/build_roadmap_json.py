#!/usr/bin/env python3
import json
import re
from pathlib import Path


HEADER_RE = re.compile(r"^##\s+Этап\s+([A-Za-z0-9]+)\s*[—-]\s*(.+)$")
ITEM_RE = re.compile(r"^\d+\.\s+(.+?)\s*(?:-\s*готово)?\s*[;.]?\s*$", re.IGNORECASE)
ITEM_DONE_RE = re.compile(r"-\s*готово\s*[;.]?\s*$", re.IGNORECASE)
ITEM_PARTIAL_RE = re.compile(r"-\s*в\s*работе\s*[;.]?\s*$", re.IGNORECASE)


def _finalize_stage(stage: dict) -> dict:
    total = stage.pop("_total_items", 0)
    done = stage.pop("_done_items", 0)
    partial = stage.pop("_partial_items", 0)

    if total > 0:
        raw = ((done + (0.5 * partial)) / total) * 100
        stage["progress"] = int(round(raw))
    else:
        stage["progress"] = max(0, min(int(stage["progress"]), 100))
    stage["_total_items"] = total
    stage["_done_items"] = done
    stage["_partial_items"] = partial
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
                "detail_states": [],
                "_total_items": 0,
                "_done_items": 0,
                "_partial_items": 0,
            }
            continue

        if not current:
            continue

        im = ITEM_RE.match(line)
        if im:
            current["_total_items"] += 1
            is_done = bool(ITEM_DONE_RE.search(line))
            is_partial = (not is_done) and bool(ITEM_PARTIAL_RE.search(line))
            if is_done:
                current["_done_items"] += 1
            elif is_partial:
                current["_partial_items"] += 1
            current["details"].append(im.group(1).strip())
            if is_done:
                current["detail_states"].append("done")
            elif is_partial:
                current["detail_states"].append("partial")
            else:
                current["detail_states"].append("pending")

    if current:
        stages.append(_finalize_stage(current))
    return stages


def calculate_overall_progress(stages: list[dict]) -> int:
    total_items = 0
    done_items = 0.0
    for stage in stages:
        total_items += int(stage.get("_total_items", 0) or 0)
        done_items += float(stage.get("_done_items", 0) or 0)
        done_items += 0.5 * float(stage.get("_partial_items", 0) or 0)

    if total_items == 0:
        return 0

    raw = (done_items / total_items) * 100
    return max(0, min(100, int(round(raw))))


def main():
    md_path = Path("/home/sadmin/.hermes/skills/manageengine-fsm/manageengine-telegram-monitor-ROADMAP.md")
    out_path = Path("/home/sadmin/.hermes/skills/manageengine-fsm/roadmap.json")
    text = md_path.read_text(encoding="utf-8")
    stages = parse(text)
    total_items = sum(int(s.get("_total_items", 0) or 0) for s in stages)
    done_items = sum(int(s.get("_done_items", 0) or 0) for s in stages)
    partial_items = sum(int(s.get("_partial_items", 0) or 0) for s in stages)
    payload = {
        "overall_progress": calculate_overall_progress(stages),
        "overall_done_items": done_items,
        "overall_partial_items": partial_items,
        "overall_total_items": total_items,
        "stages": [
            {
                "code": s.get("code"),
                "title": s.get("title"),
                "progress": s.get("progress"),
                "details": s.get("details", []),
                "detail_states": s.get("detail_states", []),
            }
            for s in stages
        ],
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "build_roadmap_json: "
        f"status=ok stages={len(stages)} overall={payload['overall_progress']} "
        f"done={done_items} partial={partial_items} total={total_items} output={out_path}"
    )


if __name__ == "__main__":
    main()
