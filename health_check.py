import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta


class BotHealthChecker:
    """Проверка здоровья бота"""

    def __init__(self, bot_token, admin_chat_id):
        self.bot_token = bot_token
        self.admin_chat_id = admin_chat_id
        self.last_activity = datetime.now()
        self.error_count = 0

    async def check_bot_health(self):
        """Проверка состояния бота"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                        f"https://api.telegram.org/bot{self.bot_token}/getMe"
                ) as response:
                    if response.status == 200:
                        self.error_count = 0
                        return True
                    else:
                        self.error_count += 1
                        return False
        except Exception as e:
            self.error_count += 1
            logging.error(f"Ошибка проверки здоровья: {e}")
            return False

    async def send_alert(self, message):
        """Отправка уведомления админу"""
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(
                    f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                    json={
                        "chat_id": self.admin_chat_id,
                        "text": f"🚨 ALERT: {message}\n🕐 {datetime.now()}"
                    }
                )
        except Exception as e:
            logging.error(f"Ошибка отправки уведомления: {e}")
