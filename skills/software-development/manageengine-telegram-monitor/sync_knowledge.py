#!/usr/bin/env python3
"""
Сбор базы знаний из ManageEngine SDP.
Выгружает закрытые заявки с решениями (resolutions).
Сохраняет в JSON для построения графа (graphify).
"""

import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, '/home/sadmin/.hermes/skills/manageengine-fsm')
from api_wrapper import ManageEngineAPI

# Конфигурация
OUTPUT_FILE = "/home/sadmin/.hermes/skills/manageengine-telegram-monitor/knowledge_base.json"
LOG_FILE = "/home/sadmin/.hermes/skills/manageengine-telegram-monitor/logs/knowledge_sync.log"

def log(message):
    """Простое логирование."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] {message}"
    print(log_message)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_message + "\n")
    except Exception:
        pass

def fetch_requests_with_resolutions(api: ManageEngineAPI, days_back: int = 7):
    """
    Выгрузка заявок с решениями за последние N дней.
    Использует _make_request() из api_wrapper для корректных заголовков.
    """
    log(f"Starting knowledge base sync (last {days_back} days)...")
    
    try:
        # Получаем последние заявки через API wrapper
        result = api._make_request("GET", "requests")
        
        rs = result.get("response_status", {})
        # response_status может быть списком [{'status': 'success'}] или dict
        if isinstance(rs, list):
            status = rs[0].get("status") if rs else None
        else:
            status = rs.get("status")
        if status != "success":
            log(f"❌ API Error: {result}")
            return []
        
        requests_data = result.get("requests", [])
        log(f"✅ Fetched {len(requests_data)} requests")
        
        knowledge_items = []
        for req in requests_data:
            req_id = req.get("id")
            if not req_id:
                continue
            
            # Получаем детали заявки с resolution
            detail = api._make_request("GET", f"requests/{req_id}")
            
            rs2 = detail.get("response_status", {})
            if isinstance(rs2, list):
                status2 = rs2[0].get("status") if rs2 else None
            else:
                status2 = rs2.get("status")
            if status2 != "success":
                continue
                
            request = detail.get("request", {})
            resolution = request.get("resolution", {})
            
            if resolution and resolution.get("content"):
                knowledge_items.append({
                    "request_id": req_id,
                    "subject": request.get("subject", ""),
                    "description": request.get("description", ""),
                    "category": request.get("category", {}).get("name", ""),
                    "resolution": resolution.get("content", ""),
                    "created_time": request.get("created_time", {}).get("value", ""),
                    "status": request.get("status", {}).get("name", "")
                })
        
        return knowledge_items
        
    except Exception as e:
        log(f"❌ Exception: {e}")
        return []

def main():
    api = ManageEngineAPI()
    
    # Выгружаем данные
    items = fetch_requests_with_resolutions(api, days_back=7)
    
    if not items:
        log("No new items to sync.")
        return
    
    # Сохраняем базу знаний
    try:
        # Загружаем существующую
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except FileNotFoundError:
            existing = []
        
        # Добавляем новые (по request_id)
        existing_ids = {item.get("request_id") for item in existing}
        new_items = [item for item in items if item.get("request_id") not in existing_ids]
        
        if new_items:
            existing.extend(new_items)
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
            log(f"✅ Knowledge base updated: {len(new_items)} new items added. Total: {len(existing)}")
        else:
            log("No new items to add (all already in base).")
            
    except Exception as e:
        log(f"❌ Error saving knowledge base: {e}")

if __name__ == "__main__":
    main()
