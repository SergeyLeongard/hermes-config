import os, json, requests, time
from dotenv import load_dotenv

load_dotenv(os.path.expanduser('~/.hermes/.env'))

API_KEY = os.getenv("MANAGEENGINE_API_KEY")
BASE_URL = "http://s-sd.shin-line.com/api/v3"
RAW_PATH = os.path.expanduser('~/.hermes/skills/manageengine-fsm/kb_raw.json')

HEADERS = {"Authtoken": API_KEY, "Content-Type": "application/x-www-form-urlencoded"}

def fetch_all():
    """Выгрузка ВСЕХ заявок с правильной пагинацией"""
    all_requests = []
    row_count = 50
    start_index = 1
    
    print("Начинаю полную выгрузку заявок...")
    while True:
        criteria = json.dumps({
            "list_info": {
                "row_count": row_count,
                "start_index": start_index
            }
        })
        try:
            resp = requests.get(f"{BASE_URL}/requests", headers=HEADERS, params={"input_data": criteria}, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            
            batch = data.get("requests", [])
            if not batch:
                break
                
            all_requests.extend(batch)
            print(f"  Получено: {len(batch)}. Всего: {len(all_requests)}")
            
            if not data.get("list_info", {}).get("has_more_rows", False):
                break
                
            start_index += row_count
            time.sleep(0.5) # Пауза, чтобы не спамить API
            
        except Exception as e:
            print(f"Ошибка на индексе {start_index}: {e}")
            break
            
    return all_requests

def enrich_with_resolution(requests):
    """Для закрытых заявок пробуем получить resolution (если его нет)"""
    print("Обогащение данных решениями...")
    enriched = []
    for i, req in enumerate(requests):
        # Если решение уже есть или заявка не закрыта, пропускаем
        if req.get("resolution") or req.get("status", {}).get("name") != "Закрыто":
            enriched.append(req)
            continue
            
        # Попытка получить детали заявки (где может быть resolution)
        try:
            resp = requests.get(f"{BASE_URL}/requests/{req['id']}", headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                details = resp.json().get("request", {})
                req["resolution"] = details.get("resolution")
                if i % 10 == 0: print(f"  Обработано: {i}/{len(requests)}")
        except: pass
        enriched.append(req)
    return enriched

if __name__ == "__main__":
    # 1. Выгрузка всех заявок
    all_reqs = fetch_all()
    
    if all_reqs:
        print(f"\nВсего выгружено: {len(all_reqs)}")
        
        # 2. Сохраним сырые данные
        with open(RAW_PATH, 'w', encoding='utf-8') as f:
            json.dump(all_reqs, f, ensure_ascii=False, indent=2)
        print(f"RAW -> {RAW_PATH}")
        
        # 3. Обогащение (опционально, может быть долгим)
        # enriched = enrich_with_resolution(all_reqs)
        
        # Анализ дат
        if all_reqs:
            dates = [r.get("created_time", {}).get("display_value") for r in all_reqs if r.get("created_time")]
            dates = [d for d in dates if d]
            if dates:
                print(f"Период: {min(dates)} — {max(dates)}")
    else:
        print("Заявки не найдены.")
