import json, os, re

INPUT = os.path.expanduser('~/.hermes/skills/manageengine-fsm/kb_raw.json')
OUTPUT = os.path.expanduser('~/.hermes/skills/manageengine-fsm/kb_categorized.json')

# Словарь категорий и ключевых слов
CATEGORIES = {
    "Принтер/МФУ": ["принтер", "сканер", "мфу", "печать", "картридж", "plotter", "xerox", "hp ", "epson"],
    "1С": ["1с", "1c", "база", "предприятие", "одинс"],
    "Компьютер/Железо": ["компьютер", "пк ", "монитор", "клавиатура", "мышь", "блок питания", "материнск", "процессор", "ssd", "hdd"],
    "Сеть/Интернет": ["интернет", "сеть", "связь", "vpn", "wifi", "роутер", "сервер", "udp", "tcp"],
    "ПО/Софт": ["программа", "установка", "обновление", "windows", "office", "лицензи", "активац"],
    "Почта": ["почта", "outlook", "email", "письмо", "ящик", "exchange"],
    "Безопасность": ["вирус", "антивирус", "пароль", "доступ", "блокировк", "фишинг"],
    "Телефония": ["телефон", "панасоник", "автоответчик", "звонок", "сип", "sip"]
}

def categorize(text):
    """Определение категории по тексту (регистронезависимо)"""
    if not text:
        return None
    text_lower = text.lower()
    for cat, keywords in CATEGORIES.items():
        for kw in keywords:
            if kw in text_lower:
                return cat
    return None

def process():
    with open(INPUT, 'r', encoding='utf-8') as f:
        requests = json.load(f)
    
    print(f"Обработка {len(requests)} заявок...")
    updated = []
    stats = {cat: 0 for cat in CATEGORIES.keys()}
    stats["No Category"] = 0
    
    for req in requests:
        cat = None
        # 1. Пытаемся взять из resolution (если есть)
        resolution = req.get("resolution")
        text_to_check = ""
        if resolution and isinstance(resolution, dict) and resolution.get("content"):
            text_to_check = resolution.get("content")
        else:
            # 2. Если resolution пуст, берем subject + description
            text_to_check = (req.get("subject") or "") + " " + (req.get("description") or "")
            
        if text_to_check:
            cat = categorize(text_to_check)
            
        req["derived_category"] = cat
        updated.append(req)
        if cat:
            stats[cat] += 1
        else:
            stats["No Category"] += 1
            
    # Сохраняем
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(updated, f, ensure_ascii=False, indent=2)
        
    print(f"✅ Категоризация завершена. Результат: {OUTPUT}")
    print("\nСтатистика:")
    for k, v in stats.items():
        if v > 0:
            print(f"  {k}: {v}")

if __name__ == "__main__":
    process()
