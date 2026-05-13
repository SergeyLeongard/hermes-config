# monitor.py patches log

Patches that need to be applied to `/home/sadmin/.hermes/skills/software-development/manageengine-telegram-monitor/monitor.py`.

## 2026-05-09: Add kaspi to category 604 (line 49)

**Before:**
```python
    "604": ["программ", "софт", "ПО", "archicad", "archi", "архикад", "архи кад", "excel", "ексел", "word", "ворд", "powerpoint", "office", "офис", "visio", "проект", "project"],
```

**After:**
```python
    "604": ["программ", "софт", "ПО", "archicad", "archi", "архикад", "архи кад", "excel", "ексел", "word", "ворд", "powerpoint", "office", "офис", "visio", "проект", "project", "каспи", "kaspi"],
```

**Reason:** Kaspi (банковское/платёжное ПО) — частый запрос от пользователей, не попадал ни под одну категорию → падал в Прочее → триггерил auto_create_category с timeout.
