---
description: Получить и показать короткую сводку оркестрации Hermes
---

# Отчет По Оркестрации

Сделай действие, а не инструкцию:

1. Подключись к `Hermesagent` по SSH alias.
2. Выполни:

```bash
set -a; . /home/sadmin/.hermes/.env.dispatcher; . /home/sadmin/.hermes/.env 2>/dev/null; set +a; /usr/bin/env python3 /home/sadmin/.hermes/hermes-agent/scripts/orchestration_report.py
```

3. Верни сюда итоговую сводку в оригинальном виде и короткий вывод: что OK и где FAIL/STALE.

Если команда не выполнилась, верни точную ошибку и следующий шаг для исправления.
