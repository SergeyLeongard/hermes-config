Telegram bot интеграция с ManageEngine ServiceDesk Plus: маппинг пользователей - Telegram user_id → IDTelegramUser (в СДП) → Отображаемое имя или email (опционально)
§
IT support staff in Telegram group: Шацких Александр (@vlupilin007, ID: 387861683), Нурберген Сауриков (@northmund95). Messages from them are ignored by the bot.
§
Updated category mapping in ManageEngine: ERP → 1С (ID: 613). Added new categories: IoT (614), VPN (615). Auto-creation of categories in ME SDP is APPROVED by user.
§
Telegram test group "ТестИттехпод" ID: -1003990457960. This is the main testing ground for the manageengine-telegram-monitor skill.
§
Bot communication style (confirmed): brief, technical, no fluff, no emojis in responses. Respond only with short statuses like "Заявка №XXXX создана. Категория: Сеть". No greetings, no thanks, no long explanations.
§
Knowledge base plan: Stages 5-6 involve extracting resolutions from ME SDP API, building a graph database (graphify), and eventually replacing first-line support with automated suggestions based on historical incident→resolution mappings.
§
execute_code sandbox lacks MANAGEENGINE_API_KEY env var. Workaround: retrieve via terminal ('env | grep MANAGEENGINE') first, then pass explicitly. API key value: DC94EDFB-0220-47EA-B5FA-93EFCC866563.
§
ME SDP file upload endpoint: POST /api/v3/requests/{id}/upload with multipart file upload. Returns 201 on success. NOT /api/v3/requests/{id}/attachments (returns 404).
§
Category keyword expansions (ongoing): 604(+excel,ексел,word,ворд,powerpoint,office,visio,проект,project,каспи,kaspi),
§
Группа ТестИттехпод: все участники теперь админы. Неправильные инциденты нужно комментировать и закреплять (pin) для отслеживания. Формат ответа при создании инцидента — строго 5 строк.