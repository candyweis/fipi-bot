# -*- coding: utf-8 -*-
"""
Утилиты для ФИПИ-бота с системным ChromeDriver
"""
import logging
import os
import time
import json
from typing import Dict, List, Optional
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import OGE_SUBJECTS, EGE_SUBJECTS

log = logging.getLogger("FIPI-Bot")

def create_webdriver():
    """Создание WebDriver с системным ChromeDriver"""
    try:
        # Системный ChromeDriver
        chromedriver_path = "/usr/local/bin/chromedriver"
        
        if not os.path.exists(chromedriver_path):
            raise Exception(f"Системный ChromeDriver не найден: {chromedriver_path}")
        
        # Опции Chrome для сервера
        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--disable-extensions")
        opts.add_argument("--disable-images")
        opts.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36")
        opts.add_argument("--window-size=1920,1080")
        opts.add_argument("--log-level=3")
        
        # Создаем сервис и драйвер
        service = Service(chromedriver_path)
        driver = webdriver.Chrome(service=service, options=opts)
        
        driver.set_page_load_timeout(60)
        driver.implicitly_wait(10)
        
        log.info(f"WebDriver создан с системным ChromeDriver: {chromedriver_path}")
        return driver
        
    except Exception as e:
        log.error(f"Ошибка создания WebDriver: {e}")
        raise

def subj_by_url(url: str) -> str:
    """Определяет точное название предмета по URL"""
    try:
        # Импортируем конфигурации
        from config import OGE_SUBJECTS, EGE_SUBJECTS
        
        # Сначала ищем в ОГЭ предметах
        for subject_name, subject_url in OGE_SUBJECTS.items():
            if subject_url == url:
                return f"ОГЭ {subject_name}"
        
        # Потом в ЕГЭ предметах  
        for subject_name, subject_url in EGE_SUBJECTS.items():
            if subject_url == url:
                return f"ЕГЭ {subject_name}"
        
        # Если точное совпадение не найдено, пытаемся найти по proj параметру
        if "proj=" in url:
            proj_id = url.split("proj=")[1].split("&")[0]
            
            # Ищем по proj_id в ОГЭ
            for subject_name, subject_url in OGE_SUBJECTS.items():
                if proj_id in subject_url:
                    return f"ОГЭ {subject_name}"
            
            # Ищем по proj_id в ЕГЭ
            for subject_name, subject_url in EGE_SUBJECTS.items():
                if proj_id in subject_url:
                    return f"ЕГЭ {subject_name}"
        
        # Если ничего не найдено, возвращаем общие названия
        if "oge.fipi.ru" in url:
            return "ОГЭ (неизвестный предмет)"
        elif "ege.fipi.ru" in url:
            return "ЕГЭ (неизвестный предмет)"
        else:
            return "Неизвестный предмет"
            
    except Exception as e:
        log.error(f"Ошибка определения предмета по URL {url}: {e}")
        return "Ошибка определения предмета"
            
    except Exception as e:
        log.error(f"Ошибка определения предмета по URL {url}: {e}")
        return "Неизвестный предмет"

def get_current_count(url: str) -> Optional[int]:
    """Точный подсчет количества заданий"""
    driver = None
    try:
        driver = create_webdriver()
        driver.get(url)
        time.sleep(3)
        
        # Сброс фильтров
        try:
            btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CLASS_NAME, "button-clear"))
            )
            driver.execute_script("arguments[0].click();", btn)
            time.sleep(2)
        except:
            pass
        
        # Получаем точное количество через pagination
        try:
            pager = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "top_pager"))
            )
            
            # Получаем номер последней страницы
            btns = pager.find_elements(By.XPATH, ".//li[@class='button']")
            if not btns:
                # Одна страница
                iframe = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "iframe"))
                )
                driver.switch_to.frame(iframe)
                tasks = driver.find_elements(By.XPATH, "//div[starts-with(@id,'q')]")
                return len(tasks)
            
            last_page = int(btns[-1].get_attribute("p"))
            
            # Считаем задачи на всех страницах кроме последней
            total_count = 0
            
            # Считаем задачи на первой странице (уже загружена)
            iframe = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "iframe"))
            )
            driver.switch_to.frame(iframe)
            tasks = driver.find_elements(By.XPATH, "//div[starts-with(@id,'q')]")
            tasks_per_page = len(tasks)
            driver.switch_to.default_content()
            
            if last_page == 1:
                return tasks_per_page
            
            # Переходим на последнюю страницу для точного подсчета
            last_btn = btns[-1]
            driver.execute_script("arguments[0].click();", last_btn)
            time.sleep(3)
            
            iframe = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "iframe"))
            )
            driver.switch_to.frame(iframe)
            last_page_tasks = driver.find_elements(By.XPATH, "//div[starts-with(@id,'q')]")
            last_page_count = len(last_page_tasks)
            
            # ИСПРАВЛЕННЫЙ расчет: (полные страницы * задач на странице) + задачи на последней
            total_count = (last_page - 1) * tasks_per_page + last_page_count
            
            log.info(f"Точный подсчет для {url}: {total_count} (страниц: {last_page}, на странице: {tasks_per_page}, на последней: {last_page_count})")
            return total_count
            
        except Exception as e:
            log.warning(f"Ошибка точного подсчета для {url}: {e}")
            return None
            
    except Exception as e:
        log.error(f"Ошибка подсчета для {url}: {e}")
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass


def split_message(text: str, max_length: int = 4096) -> List[str]:
    """Разбивает длинное сообщение на части"""
    if len(text) <= max_length:
        return [text]
    
    parts = []
    current_part = ""
    
    lines = text.split('\n')
    
    for line in lines:
        if len(current_part) + len(line) + 1 <= max_length:
            if current_part:
                current_part += '\n' + line
            else:
                current_part = line
        else:
            if current_part:
                parts.append(current_part)
                current_part = line
            else:
                # Если одна строка слишком длинная, разбиваем её
                while len(line) > max_length:
                    parts.append(line[:max_length])
                    line = line[max_length:]
                current_part = line
    
    if current_part:
        parts.append(current_part)
    
    return parts

def send_changes_file(changes_data: Dict, filename: str = "changes.json") -> str:
    """Создает файл с изменениями и возвращает путь к нему"""
    try:
        filepath = f"/tmp/{filename}"
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(changes_data, f, ensure_ascii=False, indent=2)
        
        log.info(f"Файл изменений создан: {filepath}")
        return filepath
        
    except Exception as e:
        log.error(f"Ошибка создания файла изменений: {e}")
        return None

def format_time_diff(seconds: int) -> str:
    """Форматирует разность времени в читаемый вид"""
    if seconds < 60:
        return f"{seconds} сек"
    elif seconds < 3600:
        return f"{seconds // 60} мин {seconds % 60} сек"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours} ч {minutes} мин"

def validate_url(url: str) -> bool:
    """Проверяет корректность URL ФИПИ"""
    return ("oge.fipi.ru" in url or "ege.fipi.ru" in url) and "bank/index.php" in url

def get_subject_type(url: str) -> str:
    """Определяет тип экзамена (ОГЭ/ЕГЭ) по URL"""
    if "oge.fipi.ru" in url:
        return "ОГЭ"
    elif "ege.fipi.ru" in url:
        return "ЕГЭ"
    else:
        return "Неизвестно"

# Заглушки для совместимости (если нужны)
def get_task_count_quick(url: str) -> Optional[int]:
    """Алиас для get_current_count"""
    return get_current_count(url)
