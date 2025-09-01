import asyncio
import logging
import psutil
from datetime import datetime

log = logging.getLogger("WebDriverMonitor")


class WebDriverMonitor:
    """Мониторинг состояния WebDriver процессов"""

    def __init__(self):
        self.chrome_processes = {}
        self.alerts_sent = {}

    async def start_monitoring(self):
        """Запуск мониторинга"""
        while True:
            try:
                await self.check_chrome_processes()
                await self.check_memory_usage()
                await asyncio.sleep(30)  # Проверка каждые 30 секунд
            except Exception as e:
                log.error(f"Ошибка мониторинга: {e}")
                await asyncio.sleep(60)

    async def check_chrome_processes(self):
        """Проверка Chrome процессов"""
        chrome_count = 0
        total_memory = 0

        for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
            if proc.info['name'] in ['chrome', 'chromium']:
                chrome_count += 1
                total_memory += proc.info['memory_info'].rss / 1024 / 1024  # MB

        if chrome_count > 10:  # Слишком много процессов
            log.warning(f"Много Chrome процессов: {chrome_count}")
            await self.cleanup_chrome_processes()

        log.info(f"Chrome процессов: {chrome_count}, память: {total_memory:.1f} MB")

    async def cleanup_chrome_processes(self):
        """Очистка зависших Chrome процессов"""
        cleaned = 0
        for proc in psutil.process_iter(['pid', 'name', 'create_time']):
            try:
                # Завершаем старые процессы (>1 часа)
                if (proc.info['name'] in ['chrome', 'chromium'] and
                        datetime.now().timestamp() - proc.info['create_time'] > 3600):
                    proc.terminate()
                    cleaned += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        if cleaned > 0:
            log.info(f"Очищено старых Chrome процессов: {cleaned}")


# Добавьте в main.py
monitor = WebDriverMonitor()
asyncio.create_task(monitor.start_monitoring())
