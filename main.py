# -*- coding: utf-8 -*-
"""
Главный файл запуска ФИПИ-бота
"""
import logging
import asyncio
import signal
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from config import BOT_TOKEN, CHECK_INTERVAL
from handlers import (start_cmd, status_cmd, handle_text_message,
                      on_shutdown, on_error)
from periodic_tasks import periodic_check, daily_cleanup
from queue_manager import process_queue_manager, shutdown_executor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

log = logging.getLogger("FIPI-Bot")

queue_task = None
application_instance = None


def get_application_context():
    """Возвращает контекст приложения для использования в периодических задачах"""
    return application_instance if application_instance else None


async def on_startup(context):
    """Инициализация при старте"""
    global queue_task
    log.info("🤖 Бот инициализирован, запуск систем...")
    queue_task = asyncio.create_task(process_queue_manager())
    log.info(f"⏰ Автоматические проверки каждые {CHECK_INTERVAL} секунд")


async def cleanup():
    """Очистка ресурсов при завершении"""
    global queue_task

    log.info("🧹 Начало очистки ресурсов...")

    if queue_task and not queue_task.done():
        queue_task.cancel()
        try:
            await queue_task
        except asyncio.CancelledError:
            log.info("⏹️ Менеджер очереди остановлен")

    await shutdown_executor()
    log.info("✅ Очистка ресурсов завершена")


def signal_handler(signum, frame):
    """Обработчик системных сигналов"""
    log.info(f"📡 Получен сигнал {signum}, начинаем корректное завершение")
    loop = asyncio.get_event_loop()
    loop.create_task(cleanup())


def main():
    global application_instance

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    app = Application.builder().token(BOT_TOKEN).build()
    application_instance = app

    # Обработчики команд
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("stop", on_shutdown))

    # Обработчик текстовых сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    # Периодические задачи
    app.job_queue.run_once(on_startup, when=0)
    app.job_queue.run_repeating(periodic_check, interval=CHECK_INTERVAL, first=30)  # Проверка каждую минуту
    app.job_queue.run_repeating(daily_cleanup, interval=86400, first=3600)  # Очистка каждые 24 часа, первая через час

    # Обработка ошибок
    app.add_error_handler(on_error)

    print("🤖 ФИПИ-бот запущен с автоматическими проверками!")
    print(f"⏰ Проверка изменений каждые {CHECK_INTERVAL} секунд")
    print("🧹 Ежедневная очистка данных активирована")

    try:
        app.run_polling(drop_pending_updates=True)
    except KeyboardInterrupt:
        log.info("⏹️ Получен сигнал завершения")
    finally:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.run_until_complete(cleanup())


if __name__ == "__main__":
    main()
