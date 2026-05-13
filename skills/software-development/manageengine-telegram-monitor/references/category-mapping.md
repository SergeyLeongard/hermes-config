# ManageEngine SDP Category Mapping

Updated: 2026-05-09

## Current Categories (API IDs)

| ID  | Name (RU) | Name (EN) | Keywords (stems) |
|-----|-----------|-----------|----------|
| 301 | wms | WMS | wms |
| 601 | Принтера | Printer | принтер, печать, печата, картридж, мфу, печатает, не печатает |
| 602 | ПК/Железо | PC/Hardware | компьютер, пк, мышь, мышка, клавиатура, монитор, железо, выключается |
| 603 | Telegram | Telegram | telegram |
| 604 | ПО | Software | по, software, офис, office, активация, лицензия, archicad, archi, архив кад, архи кад, софт, программ, excel, ексел, word, ворд, powerpoint, visio, проект, project, каспи, kaspi |
| 605 | Сеть | Network | интернет, сеть, wifi, wi-fi, связь, локалка, кабел, оптик, патчкорд, пачкурд, розетк |
| 606 | Почта | Email | почта, email, outlook, письм, ящик, почтов |
| 607 | Доступ | Access | пароль, доступ, права, логин, вход, учетк, пропуск, карточк, прописк |
| 608 | Телефония | Telephony | телефон, атс, звонок, gsm, сим, мобильн |
| 609 | ERP | ERP | (legacy — use 613) |
| 610 | Веб-сайт | Website | сайт, домен, веб, http, https |
| 611 | Безопасность | Security | вирус, антивирус, фишинг, подозритель, безопасност |
| 612 | Прочее | Other | (default — no keywords) |
| 613 | 1С | 1C | 1с, 1c, erp, ерп, баз, бд, отчет, отчёт, проводка, 1с:предприятие |
| 614 | IoT | IoT | iot, интернет вещей, датчик, умный дом, умное устройство, камер |
| 615 | VPN | VPN | vpn, виртуальная сеть, удаленный доступ, туннель, рдс, rds, remote desktop, удаленк |

## Keyword Design Rules

**CRITICAL: Use stems, not full words.** The matching is `keyword in text_lower` (substring).
Russian declensions require stems to match all forms:

- `"баз"` → база, базу, базы, базой, базам
- `"отчет"` → отчет, отчёт, отчеты, отчёты
- `"печата"` → печатает, печать, напечатать
- `"почтов"` → почтовый, почтовая, почтовое
- `"мобильн"` → мобильный, мобильная, мобильное

**Include both scripts for abbreviations:**
- ERP: `"erp"` + `"ерп"`
- 1С: `"1с"` + `"1c"`

## Auto-Creation Policy

**ALLOWED** (user decision 2026-05-07):
- Use `POST /api/v3/categories` to create new categories on-the-fly
- Update `CATEGORY_KEYWORDS` in `monitor.py` dynamically

## Category in Templates

**CRITICAL:** Categories created via API still require template layout configuration:
1. Go to Admin → Templates → Default Request → Layout
2. Add "Category" field to the form
3. Without this step, API returns "Неверный ввод" for category field

## UDF Field
- **Field Name:** `udf_sline_301`
- **Label in UI:** IDUserTelegram
- **Purpose:** Store Telegram user_id
- **Format:** Numeric string (e.g., "669079966")
