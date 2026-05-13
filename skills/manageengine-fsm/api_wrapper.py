#!/usr/bin/env python3
"""
ManageEngine Service Desk Plus API Wrapper
Поддерживает создание заявок с UDF и категориями.
"""

import os
import json
import requests
from typing import Optional, Dict, Any

class ManageEngineAPI:
    def __init__(self):
        self.base_url = os.getenv("MANAGEENGINE_URL", "http://s-sd.shin-line.com")
        self.api_key = os.getenv("MANAGEENGINE_API_KEY")
        self.default_email = os.getenv("MANAGEENGINE_DEFAULT_EMAIL", "")
        self.default_group = os.getenv("MANAGEENGINE_DEFAULT_GROUP", "")
        self.default_group_id = os.getenv("MANAGEENGINE_DEFAULT_GROUP_ID", "").strip()
        self.user_mapping_path = os.getenv(
            "USER_MAPPING_PATH",
            "/home/sadmin/.hermes/skills/manageengine-fsm/user_mapping.json",
        )
        
        if not self.api_key:
            raise ValueError("MANAGEENGINE_API_KEY not set")
        
        self.form_headers = {
            "Authtoken": self.api_key,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        self.auth_headers = {
            "Authtoken": self.api_key,
        }
    
    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """Выполнение запроса к API."""
        url = f"{self.base_url}/api/v3/{endpoint}"
        
        if data:
            # API expects input_data as form-encoded string
            input_data_str = json.dumps(data)
            payload = {"input_data": input_data_str}
        else:
            payload = None
        
        try:
            method_upper = method.upper()
            if method_upper == "GET":
                response = requests.get(url, headers=self.form_headers, timeout=30)
            elif method_upper == "POST":
                response = requests.post(url, headers=self.form_headers, data=payload, timeout=30)
            elif method_upper == "PUT":
                response = requests.put(url, headers=self.form_headers, data=payload, timeout=30)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e), "response_status": {"status": "failed"}}
    
    def find_user_by_telegram_id(self, telegram_user_id: str) -> Optional[str]:
        """Return requester_id from local ID mapping, fallback to sadmin."""
        default_requester = "1011"  # sadmin
        telegram_id = str(telegram_user_id or "").strip()
        if not telegram_id:
            return default_requester

        try:
            with open(self.user_mapping_path, "r", encoding="utf-8") as f:
                mapping_data = json.load(f)
        except Exception:
            return default_requester

        by_id = (
            mapping_data.get("mapping", {})
            .get("by_telegram_user_id", {})
        )
        entry = by_id.get(telegram_id)
        if not isinstance(entry, dict):
            return default_requester

        requester_id = str(entry.get("requester_id", "")).strip()
        return requester_id if requester_id else default_requester
    
    def create_request(self, subject: str, description: str, 
                      requester_id: str = "1011",
                      category_id: Optional[str] = None,
                      udf_fields: Optional[Dict] = None,  # Например: {"udf_sline_301": "telegram_id"}
                      priority: Optional[int] = None) -> Dict[str, Any]:
        """
        Создание заявки в ManageEngine.
        
        Args:
            subject: Тема заявки
            description: Описание
            requester_id: ID пользователя в ME
            category_id: ID категории (опционально)
            udf_fields: Словарь с UDF полями (опционально)
            priority: Приоритет (1-4, опционально)
        """
        request_data = {
            "request": {
                "subject": subject[:100],  # Ограничение ME
                "description": description,
                "requester": {"id": requester_id}
            }
        }
        
        # Добавляем категорию, если указана
        if category_id:
            request_data["request"]["category"] = {"id": category_id}
        
        # Добавляем UDF поля, если указаны
        if udf_fields:
            request_data["request"]["udf_fields"] = udf_fields

        # Добавляем группу поддержки по умолчанию (если задана)
        if self.default_group_id:
            request_data["request"]["group"] = {"id": str(self.default_group_id)}
        elif self.default_group:
            request_data["request"]["group"] = {"name": self.default_group}
        
        # Добавляем приоритет, если указан
        if priority:
            request_data["request"]["priority"] = priority
        
        return self._make_request("POST", "requests", request_data)
    
    def get_request_status(self, request_id: str) -> Dict[str, Any]:
        """Получение статуса заявки."""
        return self._make_request("GET", f"requests/{request_id}")
    
    def search_requests(self, query: str) -> Dict[str, Any]:
        """Поиск заявок по ключевым словам."""
        search_data = json.dumps({"search_fields": {"subject": query}})
        return self._make_request("GET", f"requests?input_data={search_data}")




    def update_request(self, request_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обновление существующей заявки.
        
        Args:
            request_id: ID заявки
            update_data: Словарь с полями для обновления
        """
        return self._make_request("PUT", f"requests/{request_id}", {"request": update_data})
    
    def add_to_description(self, request_id: str, additional_text: str) -> Dict[str, Any]:
        """
        Добавление текста к описанию существующей заявки.
        
        Args:
            request_id: ID заявки
            additional_text: Текст для добавления
        """
        # Получаем текущую заявку
        current = self._make_request("GET", f"requests/{request_id}")
        
        if current.get("response_status", {}).get("status") != "success":
            return current
        
        current_desc = current.get("request", {}).get("description", "")
        new_description = current_desc + "\n\n[Telegram Update]\n" + additional_text
        
        return self.update_request(request_id, {"description": new_description})

    def _post_multipart(self, endpoint: str, data: Dict[str, Any], file_path: str, file_key: str) -> requests.Response:
        """Отправка multipart/form-data с вложением."""
        url = f"{self.base_url}/api/v3/{endpoint}"
        with open(file_path, "rb") as fh:
            files = {file_key: (os.path.basename(file_path), fh, "application/octet-stream")}
            return requests.post(url, headers=self.auth_headers, data=data, files=files, timeout=30)

    def attach_file_to_request(self, request_id: str, file_path: str, note_text: str = "Attachment from Telegram") -> Dict[str, Any]:
        """
        Прикрепление файла к заявке.
        Пробует совместимые комбинации endpoint/field для разных сборок SDP.
        """
        if not os.path.exists(file_path):
            return {
                "error": f"file not found: {file_path}",
                "response_status": {"status": "failed"}
            }

        note_body = {"note": {"description": note_text}}
        attempts = [
            {
                "name": "upload+file",
                "endpoint": f"requests/{request_id}/upload",
                "data": {},
                "file_key": "file",
            },
            {
                "name": "notes+file",
                "endpoint": f"requests/{request_id}/notes",
                "data": {"input_data": json.dumps(note_body, ensure_ascii=False)},
                "file_key": "file",
            },
            {
                "name": "notes+attachments[]",
                "endpoint": f"requests/{request_id}/notes",
                "data": {"input_data": json.dumps(note_body, ensure_ascii=False)},
                "file_key": "attachments[]",
            },
            {
                "name": "attachments+file",
                "endpoint": f"requests/{request_id}/attachments",
                "data": {},
                "file_key": "file",
            },
            {
                "name": "attachments+attachments[]",
                "endpoint": f"requests/{request_id}/attachments",
                "data": {},
                "file_key": "attachments[]",
            },
        ]

        errors = []
        for attempt in attempts:
            try:
                resp = self._post_multipart(
                    endpoint=attempt["endpoint"],
                    data=attempt["data"],
                    file_path=file_path,
                    file_key=attempt["file_key"],
                )
            except requests.exceptions.RequestException as exc:
                errors.append({"attempt": attempt["name"], "error": str(exc)})
                continue

            body_text = resp.text or ""
            parsed = None
            if body_text:
                try:
                    parsed = resp.json()
                except ValueError:
                    parsed = None

            if resp.ok:
                if parsed is None:
                    return {"response_status": {"status": "success"}, "attempt": attempt["name"], "raw": body_text}
                status = parsed.get("response_status", {}).get("status")
                if status in (None, "success"):
                    attachment_id = (parsed.get("attachment") or {}).get("id")
                    if attachment_id:
                        current = self.get_request_status(request_id)
                        existing = (current.get("request") or {}).get("attachments") or []
                        merged = []
                        seen = set()
                        for item in existing:
                            eid = str(item.get("id", "")).strip()
                            if eid and eid not in seen:
                                merged.append({"id": eid})
                                seen.add(eid)
                        nid = str(attachment_id)
                        if nid not in seen:
                            merged.append({"id": nid})
                        link = self.update_request(request_id, {"attachments": merged})
                        link_status = (link.get("response_status") or {}).get("status")
                        if link_status == "success":
                            parsed["attempt"] = attempt["name"]
                            parsed["linked"] = True
                            return parsed
                        errors.append({
                            "attempt": attempt["name"] + "->link",
                            "status": link_status,
                            "body": json.dumps(link, ensure_ascii=False)[:800],
                        })
                        continue
                    parsed["attempt"] = attempt["name"]
                    return parsed

            errors.append({
                "attempt": attempt["name"],
                "status_code": resp.status_code,
                "body": body_text[:800],
            })

        return {
            "error": "all attachment endpoints failed",
            "response_status": {"status": "failed"},
            "details": errors,
        }


if __name__ == "__main__":
    # Тест создания заявки
    api = ManageEngineAPI()
    
    # Базовая заявка (без UDF и категорий, если они не настроены)
    result = api.create_request(
        subject="Тестовая заявка из wrapper (базовая)",
        description="Описание заявки через API Wrapper",
        requester_id="1011"
    )
    
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # Если настроены UDF и категории, можно раскомментировать:
    """
    udf = {
        "udf_char1": "Telegram User: @test_user",
    }
    
    result2 = api.create_request(
        subject="Тест с UDF и категорией",
        description="Проверка доп. полей",
        requester_id="1011",
        category_id="301",  # wms
        udf_fields=udf
    )
    print(json.dumps(result2, indent=2, ensure_ascii=False))
    """
