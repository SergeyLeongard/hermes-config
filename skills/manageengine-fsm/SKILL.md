---
name: manageengine-fsm
description: "Обработка заявок ManageEngine через Telegram с FSM (конечный автомат состояний). MVP: регекс-логика + API Wrapper."
category: software-development
---

# ManageEngine FSM Integration

**⚠️ CRITICAL: FSM (Finite State Machine) design is MANDATORY for bot stability.** User emphasized this repeatedly.

## User Mapping (CORRECTED)
Telegram user_id → IDTelegramUser (in ME SDP) → Display name or email (optional)
- DO NOT map directly to email only
- Store mapping in `~/.hermes/skills/manageengine-fsm/user_mapping.json`

## Триггеры
- Любое текстовое сообщение в Telegram (кроме команд `/new`, `/status`, `/help`).
- Голосовые сообщения (требуют STT, пока заглушка).

## FSM Состояния (State Machine)
Хранится в `~/.hermes/skills/manageengine-fsm/states.json`.

1. `idle` — Ожидание. Бот готов.
2. `collecting_issue` — Сбор текста проблемы. Юзер пишет "Сломался принтер".
3. `confirming` — Бот показывает: "Тема: [Заголовок]. Создать? (Да/Нет)".
4. `creating_ticket` — Идет запрос к API ManageEngine.
5. `waiting_resolution` — Заявка создана, ждем решения (проверка статуса по крону или команде /status).
6. `fallback` — Если API недоступен или ошибка парсинга.

## Логика (MVP)
- **Regex:** "срочно", "упал" -> priority=High. "принтер", "печать" -> category=Hardware.
- **LLM (Hermes):** Только для генерации поля `subject` (заголовка) из длинного текста.
- **Anti-duplicate:** Перед созданием вызвать `search_requests` по ключевым словам.

## Runtime Response Contract (STRICT)
- Ответ пользователю ОДНОЙ строкой с кликабельной ссылкой на ServiceDesk:
  - `Заявка №<id> создана. Категория: <Название>. [Открыть](http://s-sd.shin-line.com/WorkOrder.do?woMode=viewWO&WOID=<id>)`
  - `Добавлено к заявке №<id>. [Открыть](http://s-sd.shin-line.com/WorkOrder.do?woMode=viewWO&WOID=<id>)`
  - `С каким ПО или оборудованием проблема?`
  - `Опишите проблему текстом, пожалуйста.`
- Запрещено: многострочные шаблоны с эмодзи (👤📝🏷🆔), приветствия, пояснения, советы.
- Если в сообщении 2+ проблемы, создавать инцидент по основной проблеме из первой части сообщения.
- Если сообщение содержит фото/документы, прикреплять все вложения к созданной/активной заявке.
- В ответе всегда использовать `telegram_user_id` как значение UDF `udf_sline_301`.
- Ссылка `http://s-sd.shin-line.com/WorkOrder.do?woMode=viewWO&WOID=<id>` добавляется ВСЕГДА, когда есть request_id.

## Использование
Скрипт `api_wrapper.py` читает переменные из `~/.hermes/.env`:
- `MANAGEENGINE_URL` (default: http://s-sd.shin-line.com/)
- `MANAGEENGINE_API_KEY`
- `MANAGEENGINE_DEFAULT_EMAIL`

## API Pitfalls (ManageEngine SDP v3)

1. **Data Format:** API expects `input_data` as form-encoded string, NOT JSON body.
   ```python
   # CORRECT:
   input_data_str = json.dumps(request_data)
   requests.post(url, headers=HEADERS, data={"input_data": input_data_str})
   
   # WRONG:
   # requests.post(url, headers=HEADERS, json=request_data)
   ```

2. **User Identification:** Use `id` (numeric string), not `email_id` in `requester` object.
   ```python
   "requester": {"id": "1011"}  # CORRECT
   # "requester": {"email_id": "..."}  # WRONG - causes "Неверный ввод"
   ```

3. **Response Parsing:** Returns `"requests"` array in response, NOT `"details"`.
   ```python
   data.get("requests", [])  # CORRECT
   # data.get("details", [])  # WRONG
   ```

4. **Priority Field:** Passing `priority` as int may cause "Unable to parse the JSON" error. Omit if not needed or verify format.

5. **Headers:** Use `Authtoken` header for auth, not URL parameters. Content-Type should be `application/x-www-form-urlencoded` for form data.



6. **Categories:** Category must be an object with `id` field. Requires template configuration in Admin -> Templates -> Default Request -> Layout.
   ```python
   "category": {"id": "301"}  # CORRECT - ID from GET /api/v3/categories
   # "category": "301"         # WRONG - causes "Unable to parse the JSON"
   ```

7. **UDF Fields:** Custom fields (udf_fields) must be added to the template first (Admin -> Templates -> Layout). 
   - **ACTUAL FIELD NAME (this instance):** `udf_sline_301` (labeled "IDUserTelegram" in UI)
   - Field names are NOT standardized (not always `udf_char1`, `udf_char2`, etc.)
   - Check actual field name in Admin -> Incident Management -> Incident -> Additional Fields
   ```python
   "udf_fields": {
       "udf_sline_301": "669079966"  # Telegram user_id
   }
   ```

8. **Categories in Templates:** Categories added via API (POST /api/v3/categories) still require template layout configuration.
    - Go to Admin -> Templates -> Default Request -> Layout
    - Add "Category" field to the form
    - Without this step, API returns "Неверный ввод" for category field

9. **PUT Method:** Required for updating requests. Add to `_make_request()` in `api_wrapper.py`:
   ```python
   elif method.upper() == "PUT":
       response = requests.put(url, headers=headers, data=payload, timeout=30)
   ```

10. **Category Auto-Creation:** ALLOWED (user decision 2026-05-07). Use `POST /api/v3/categories` to create new categories on-the-fly.
    - Current categories: 301(wms), 601(Принтера), 602(ПК/Железо), 603(Telegram), 604(ПО), 605(Сеть), 606(Почта), 607(Доступ), 608(Телефония), 609(ERP), 610(Веб-сайт), 611(Безопасность), 612(Прочее), 613(1С), 614(IoT), 615(VPN)

## Graph Visualization
## ## Graph Visualization

The skill includes a self-contained web UI (`graph.html`) using vis.js:
- **Service:** `hermes-graph.service` (systemd user service, port 8888)
- **Data:** `graph.json` built by `build_graph.py`
- **Access:** `http://<server-ip>:8888/graph.html`
- **Features:** Interactive nodes, search filter, category clustering
