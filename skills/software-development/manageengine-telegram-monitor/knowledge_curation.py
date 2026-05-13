#!/usr/bin/env python3
"""
Weekly IT hints auto-curation.

Reads recent context messages and optionally JSONL files from CURATION_INPUT_DIR,
extracts frequent candidate tokens, and updates it_hints.json automatically.
"""

import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path("/home/sadmin/.hermes/skills/software-development/manageengine-telegram-monitor")
CONTEXT_FILE = BASE_DIR / "context.json"
HINTS_FILE = BASE_DIR / "it_hints.json"
CURATION_INPUT_DIR = Path(os.getenv("CURATION_INPUT_DIR", str(BASE_DIR / "curation_inputs")))

MIN_TOKEN_LEN = int(os.getenv("CURATION_MIN_TOKEN_LEN", "3"))
MIN_FREQ = int(os.getenv("CURATION_MIN_FREQ", "2"))
LOOKBACK_DAYS = int(os.getenv("CURATION_LOOKBACK_DAYS", "7"))
MAX_NEW_HINTS = int(os.getenv("CURATION_MAX_NEW_HINTS", "40"))

STOPWORDS = {
    "это", "как", "что", "где", "когда", "почему", "помогите", "проблема", "ошибка", "сегодня",
    "вчера", "завтра", "очень", "просто", "нужно", "можно", "надо", "опять", "всем", "коллеги",
}


def tokenize(text: str):
    for t in re.findall(r"[a-zA-Zа-яА-Я0-9_+-]{3,}", text.lower()):
        if len(t) < MIN_TOKEN_LEN or t in STOPWORDS:
            continue
        yield t


def load_hints():
    if not HINTS_FILE.exists():
        return {"hints": [], "updated_at": ""}
    try:
        return json.loads(HINTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"hints": [], "updated_at": ""}


def load_recent_texts():
    texts = []
    cutoff = datetime.now() - timedelta(days=LOOKBACK_DAYS)

    if CONTEXT_FILE.exists():
        try:
            data = json.loads(CONTEXT_FILE.read_text(encoding="utf-8"))
            for c in data.get("active_contexts", []):
                msg = str(c.get("last_message_text", "")).strip()
                ts = c.get("last_update", "")
                if not msg:
                    continue
                try:
                    d = datetime.fromisoformat(ts)
                    if d < cutoff:
                        continue
                except Exception:
                    pass
                texts.append(msg)
        except Exception:
            pass

    if CURATION_INPUT_DIR.exists():
        for p in CURATION_INPUT_DIR.glob("*.jsonl"):
            try:
                for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if not line.strip():
                        continue
                    obj = json.loads(line)
                    msg = str(obj.get("text", "")).strip()
                    is_it = obj.get("is_it")
                    if msg and is_it is True:
                        texts.append(msg)
            except Exception:
                continue

    return texts


def main():
    hints_doc = load_hints()
    existing = {h.strip().lower() for h in hints_doc.get("hints", []) if str(h).strip()}
    texts = load_recent_texts()

    counter = Counter()
    for t in texts:
        counter.update(tokenize(t))

    candidates = [tok for tok, freq in counter.most_common() if freq >= MIN_FREQ and tok not in existing]
    to_add = candidates[:MAX_NEW_HINTS]

    merged = sorted(existing.union(to_add))
    out = {
        "hints": merged,
        "updated_at": datetime.now().isoformat(),
        "stats": {
            "texts_scanned": len(texts),
            "new_hints_added": len(to_add),
        },
    }
    HINTS_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out["stats"], ensure_ascii=False))


if __name__ == "__main__":
    main()
