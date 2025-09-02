# -*- coding: utf-8 -*-
"""
Управление данными бота с кэшированием результатов
"""
import os
import json
from typing import Dict
from datetime import datetime, timedelta
from config import DATA_FILE

def ensure_store() -> Dict:
    """Создает или загружает хранилище данных"""
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "subscriptions": {},  # Подписки на изменения FIPI
                "reminder_subscriptions": {},  # Подписки на напоминания о расписании
                "last_counts": {},
                "last_ids": {},
                "historical_ids": {},
                "recent_parsing": {}  # Кэш недавних результатов
            }, f, ensure_ascii=False)
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Добавляем новые поля если их нет
    if "recent_parsing" not in data:
        data["recent_parsing"] = {}
    if "reminder_subscriptions" not in data:
        data["reminder_subscriptions"] = {}
    save_store(data)
    return data

def save_store(store: Dict):
    """Сохраняет данные в файл"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False)

def save_parsing_result(url: str, operation: str, result, user_id: str):
    """Сохраняет результат парсинга в кэш"""
    timestamp = datetime.now().isoformat()
    store["recent_parsing"][url] = {
        "timestamp": timestamp,
        "operation": operation,
        "result": list(result) if isinstance(result, set) else result,
        "user_id": user_id
    }
    save_store(store)

def get_recent_parsing(url: str, operation: str, max_age_hours: int = 2) -> Dict:
    """Получает недавний результат парсинга если он есть"""
    if url not in store.get("recent_parsing", {}):
        return None
    cached = store["recent_parsing"][url]
    # Проверяем операцию
    if cached.get("operation") != operation:
        return None
    # Проверяем возраст
    try:
        cache_time = datetime.fromisoformat(cached["timestamp"])
        max_age = timedelta(hours=max_age_hours)
        if datetime.now() - cache_time > max_age:
            # Удаляем устаревший результат
            del store["recent_parsing"][url]
            save_store(store)
            return None
    except Exception:
        return None
    return cached

def clean_old_parsing_cache():
    """Очищает устаревшие результаты парсинга"""
    current_time = datetime.now()
    max_age = timedelta(hours=6)  # Максимальный возраст 6 часов
    to_remove = []
    for url, cached in store.get("recent_parsing", {}).items():
        try:
            cache_time = datetime.fromisoformat(cached["timestamp"])
            if current_time - cache_time > max_age:
                to_remove.append(url)
        except Exception:
            to_remove.append(url)
    for url in to_remove:
        del store["recent_parsing"][url]
    if to_remove:
        save_store(store)

# Глобальное хранилище
store = ensure_store()
