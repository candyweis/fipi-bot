# -*- coding: utf-8 -*-
"""
Управление системными ресурсами
"""
import logging
import psutil
import signal
import os
from config import MAX_WEBDRIVERS

log = logging.getLogger("FIPI-Bot")

# Счетчик активных WebDriver'ов
active_webdrivers = 0


def kill_chrome_processes():
    """Убивает все процессы Chrome/Chromedriver, чтобы освободить ресурсы."""
    global active_webdrivers
    try:
        killed_count = 0
        for proc in psutil.process_iter(['name', 'pid']):
            try:
                if proc.info['name'] and proc.info['name'].lower() in ['chrome.exe', 'chromedriver.exe', 'chrome',
                                                                       'chromedriver']:
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except psutil.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                    log.info(f"Завершён процесс: {proc.info['name']} (PID: {proc.info['pid']})")
                    killed_count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if killed_count > 0:
            active_webdrivers = 0  # Сбрасываем счетчик
            log.info(f"Завершено {killed_count} Chrome процессов")
    except Exception as e:
        log.warning(f"Ошибка при завершении Chrome процессов: {e}")


def kill_zombie_processes():
    """Убивает зомби-процессы Python"""
    try:
        current_pid = os.getpid()
        killed_count = 0

        for proc in psutil.process_iter(['pid', 'name', 'status', 'ppid']):
            try:
                # Ищем зомби-процессы Python, которые могли остаться от парсинга
                if (proc.info['status'] == psutil.STATUS_ZOMBIE and
                        proc.info['name'] and 'python' in proc.info['name'].lower() and
                        proc.info['ppid'] == current_pid):
                    os.kill(proc.info['pid'], signal.SIGKILL)
                    log.info(f"Убит зомби-процесс: PID {proc.info['pid']}")
                    killed_count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                continue

        if killed_count > 0:
            log.info(f"Убито {killed_count} зомби-процессов")
    except Exception as e:
        log.warning(f"Ошибка при завершении зомби-процессов: {e}")


def check_resources() -> bool:
    """Проверяет, достаточно ли ресурсов для запуска нового WebDriver."""
    global active_webdrivers
    try:
        # Проверяем память
        mem = psutil.virtual_memory()
        if mem.percent > 90:
            log.warning(f"Недостаточно памяти: использование {mem.percent}%")
            # Пытаемся очистить ресурсы
            kill_chrome_processes()
            kill_zombie_processes()
            return False

        # Проверяем лимит WebDriver'ов
        if active_webdrivers >= MAX_WEBDRIVERS:
            log.warning(f"Достигнут лимит WebDriver'ов: {active_webdrivers}/{MAX_WEBDRIVERS}")
            return False

        # Проверяем CPU
        cpu_percent = psutil.cpu_percent(interval=1)
        if cpu_percent > 90:
            log.warning(f"Недостаточно CPU: использование {cpu_percent}%")
            return False

        # Проверяем дисковое пространство
        disk = psutil.disk_usage('/')
        if disk.percent > 95:
            log.warning(f"Недостаточно места на диске: использование {disk.percent}%")
            return False

        return True
    except Exception as e:
        log.error(f"Ошибка проверки ресурсов: {e}")
        return False


def cleanup_resources():
    """Принудительная очистка всех ресурсов"""
    log.info("Принудительная очистка ресурсов...")
    kill_chrome_processes()
    kill_zombie_processes()
    global active_webdrivers
    active_webdrivers = 0
    log.info("Очистка ресурсов завершена")
