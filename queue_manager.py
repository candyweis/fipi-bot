# -*- coding: utf-8 -*-
"""
Управление задачами парсинга - БЕЗ БЛОКИРОВКИ EVENT LOOP
"""
import asyncio
import logging
import os
import time
import psutil
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from telegram import CallbackQuery
from telegram.ext import ContextTypes
from typing import Dict

from parser import TaskIdExtractor
from database import store, save_store
from keyboards import kb_main_reply
from config import (PARSING_TIMEOUT, MAX_CONCURRENT_PARSING, MAX_CONCURRENT_AUTO_PARSING,
                    MEMORY_LIMIT_PERCENT, CPU_LIMIT_PERCENT)

log = logging.getLogger("FIPI-Bot")

# Глобальные переменные
executor = None
active_tasks: Dict[str, Dict] = {}
running_futures: Dict[str, asyncio.Future] = {}


def parsing_worker_with_progress(url: str, operation: str, chat_id: str, task_id: str):
    """Рабочая функция для парсинга в отдельном процессе"""
    try:
        log.info(f"🚀 Начало парсинга в процессе для {url}: {operation} (Task: {task_id})")

        os.environ['PARSING_PROCESS'] = '1'
        os.environ['PARSING_CHAT_ID'] = chat_id
        os.environ['PARSING_TASK_ID'] = task_id

        progress_file = f"progress_{task_id}.txt"

        def update_progress(message: str):
            try:
                with open(progress_file, "w", encoding="utf-8") as f:
                    f.write(message)
            except Exception as e:
                log.warning(f"⚠️ Ошибка записи прогресса для {task_id}: {e}")

        class ProgressExtractor(TaskIdExtractor):
            def __init__(self, progress_callback, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.progress_callback = progress_callback

            def extract_ids_sync(self, url: str):
                self.progress_callback("🚀 Парсинг начался...")
                self.start_time = time.time()

                try:
                    self.driver = self._init_driver()
                    log.info(f"📖 Начало парсинга ID для {url} (Task: {task_id})")

                    self.driver.get(url)
                    time.sleep(5)

                    try:
                        from selenium.webdriver.common.by import By
                        from selenium.webdriver.support.ui import WebDriverWait
                        from selenium.webdriver.support import expected_conditions as EC

                        btn = WebDriverWait(self.driver, self.timeout).until(
                            EC.element_to_be_clickable((By.CLASS_NAME, "button-clear"))
                        )
                        self.driver.execute_script("arguments[0].click();", btn)
                        time.sleep(3)
                        self.progress_callback("✅ Фильтры сброшены")
                    except Exception as e:
                        log.warning(f"⚠️ Не удалось сбросить фильтры для {task_id}: {e}")

                    total = self._total_pages()
                    self.progress_callback(f"📄 Найдено страниц: {total}")

                    all_ids = set()
                    failed_pages = []

                    for p in range(1, total + 1):
                        max_retries = 3
                        retry_count = 0
                        page_success = False

                        while retry_count < max_retries and not page_success:
                            try:
                                self._check_timeout()

                                if p > 1:
                                    use_input_field = retry_count > 0
                                    if not self._goto(p, use_input_field=use_input_field):
                                        raise Exception("Навигация не удалась")

                                self.progress_callback(f"📖 Страница {p}/{total}")

                                ids = self._ids_on_page()

                                if ids or p == total:
                                    all_ids.update(ids)
                                    page_success = True
                                    self.progress_callback(f"✅ Страница {p}/{total} - найдено {len(ids)} ID")
                                else:
                                    raise Exception(f"Пустая страница {p}")

                            except Exception as e:
                                retry_count += 1
                                self.progress_callback(f"⚠️ Ошибка на странице {p}, попытка {retry_count}")

                                if retry_count < max_retries:
                                    try:
                                        self.driver.quit()
                                    except:
                                        pass

                                    time.sleep(5 * retry_count)
                                    self.driver = self._init_driver()
                                    self.driver.get(url)
                                    time.sleep(5)
                                else:
                                    failed_pages.append(p)
                                    self.progress_callback(f"❌ Страница {p} пропущена")

                    if failed_pages:
                        self.progress_callback(f"⚠️ Пропущены страницы: {failed_pages}")

                    if os.environ.get('PARSING_PROCESS'):
                        timestamp = datetime.now().isoformat()
                        from database import ensure_store
                        process_store = ensure_store()
                        if url not in process_store["historical_ids"]:
                            process_store["historical_ids"][url] = []
                        process_store["historical_ids"][url].append({
                            "timestamp": timestamp,
                            "ids": list(all_ids)
                        })
                        save_store(process_store)

                    self.progress_callback(f"🎉 Парсинг завершен! Найдено {len(all_ids)} ID")
                    return all_ids

                except Exception as e:
                    self.progress_callback(f"❌ Ошибка: {str(e)[:50]}...")
                    raise e
                finally:
                    if self.driver:
                        try:
                            self.driver.quit()
                        except:
                            pass
                        self.driver = None

        extractor = ProgressExtractor(update_progress)

        if operation == "Создание файла ID":
            ids = extractor.extract_ids_sync(url)
            return {"status": "success", "result": list(ids), "error": None}
        elif operation in ["Сравнение ID", "Автоматический парсинг"]:
            current_ids = extractor.extract_ids_sync(url)
            from database import ensure_store
            process_store = ensure_store()
            prev_ids = set(process_store["last_ids"].get(url, []))
            added = current_ids - prev_ids
            removed = prev_ids - current_ids
            return {
                "status": "success",
                "result": {
                    "current_ids": list(current_ids),
                    "added": list(added),
                    "removed": list(removed)
                },
                "error": None
            }
        else:
            return {"status": "error", "result": None, "error": f"Неизвестная операция: {operation}"}

    except Exception as e:
        try:
            with open(f"progress_{task_id}.txt", "w", encoding="utf-8") as f:
                f.write(f"❌ Ошибка: {str(e)[:100]}")
        except:
            pass
        log.error(f"❌ Ошибка парсинга в процессе для {url} (Task: {task_id}): {e}", exc_info=True)
        return {"status": "error", "result": None, "error": str(e)}
    finally:
        for env_var in ['PARSING_PROCESS', 'PARSING_CHAT_ID', 'PARSING_TASK_ID']:
            if env_var in os.environ:
                del os.environ[env_var]

        try:
            os.remove(f"progress_{task_id}.txt")
        except:
            pass


async def init_executor():
    """Инициализация пула процессов"""
    global executor
    if executor is None:
        executor = ProcessPoolExecutor(max_workers=MAX_CONCURRENT_PARSING)
        log.info(f"🔧 Инициализирован пул процессов: {MAX_CONCURRENT_PARSING} workers")


async def shutdown_executor():
    """Корректное завершение пула процессов"""
    global executor
    if executor:
        log.info("🔧 Завершение пула процессов")
        executor.shutdown(wait=True, cancel_futures=True)
        executor = None


async def start_parsing_background_task(task_id: str, chat_id: str, query, url: str,
                                        operation: str, callback, is_auto: bool):
    """ФОНОВАЯ задача парсинга - НЕ БЛОКИРУЕТ EVENT LOOP"""
    try:
        task_info = {
            "task_id": task_id,
            "url": url,
            "operation": operation,
            "status": "processing",
            "start_time": datetime.now(),
            "chat_id": chat_id,
            "is_auto": is_auto
        }

        active_tasks[task_id] = task_info

        log.info(f"🚀 ФОНОВЫЙ ЗАПУСК {task_id}: {operation} для {url}")
        log.info(f"   👤 Chat ID: {chat_id}, Auto: {is_auto}")
        log.info(f"   ⚡ Всего активных задач: {len(active_tasks)}")

        if query and not is_auto:
            from utils import subj_by_url
            await query.edit_message_text(
                f"🚀 Парсинг запущен!\n"
                f"📚 {subj_by_url(url)}\n"
                f"⚡ Активных задач: {len(active_tasks)}\n"
                f"🆔 ID: {task_id[:8]}"
            )

        # Запускаем в отдельном процессе
        loop = asyncio.get_event_loop()
        future = loop.run_in_executor(
            executor,
            parsing_worker_with_progress,
            url,
            operation,
            chat_id,
            task_id
        )

        running_futures[task_id] = future

        # Запускаем мониторинг прогресса как отдельную задачу
        asyncio.create_task(monitor_parsing_progress(task_id, query, url, is_auto))

        # Ждем результат БЕЗ БЛОКИРОВКИ основного потока
        try:
            result_dict = await future
        except Exception as e:
            log.error(f"⏰ Ошибка выполнения задачи {task_id}: {e}")
            if query and not is_auto:
                await query.edit_message_text("❌ Ошибка выполнения парсинга")
            return

        if result_dict and result_dict.get("status") == "success":
            await handle_parsing_success(task_id, result_dict, query, url, operation, callback, is_auto)
        else:
            error = result_dict.get("error", "Неизвестная ошибка") if result_dict else "Пустой результат"
            await handle_parsing_error(task_id, error, query, operation, is_auto)

    except Exception as e:
        log.error(f"❌ Ошибка фоновой задачи {task_id}: {e}")
        await handle_parsing_error(task_id, str(e), query, operation, is_auto)
    finally:
        # Очищаем задачу
        if task_id in active_tasks:
            del active_tasks[task_id]
        if task_id in running_futures:
            del running_futures[task_id]

        try:
            progress_file = f"progress_{task_id}.txt"
            if os.path.exists(progress_file):
                os.remove(progress_file)
        except:
            pass

        log.info(f"✅ Фоновая задача {task_id} завершена и очищена")


async def monitor_parsing_progress(task_id: str, query, url: str, is_auto: bool):
    """Отслеживает прогресс парсинга БЕЗ БЛОКИРОВКИ"""
    progress_file = f"progress_{task_id}.txt"
    last_progress = ""

    while task_id in running_futures and not running_futures[task_id].done():
        try:
            if os.path.exists(progress_file):
                with open(progress_file, "r", encoding="utf-8") as f:
                    current_progress = f.read().strip()

                if current_progress and current_progress != last_progress and query and not is_auto:
                    try:
                        from utils import subj_by_url
                        await query.edit_message_text(
                            f"🚀 Парсинг в процессе\n"
                            f"📚 {subj_by_url(url)}\n"
                            f"📊 {current_progress}\n"
                            f"🆔 ID: {task_id[:8]}"
                        )
                    except Exception as e:
                        log.warning(f"⚠️ Ошибка обновления прогресса: {e}")
                last_progress = current_progress
        except Exception as e:
            log.warning(f"⚠️ Ошибка чтения прогресса для {task_id}: {e}")

        await asyncio.sleep(3)  # Увеличил интервал для снижения нагрузки


async def handle_parsing_success(task_id: str, result_dict: dict, query, url: str,
                                 operation: str, callback, is_auto: bool):
    """Обрабатывает успешный результат парсинга"""
    try:
        result = result_dict["result"]

        if operation == "Создание файла ID":
            from database import save_parsing_result
            save_parsing_result(url, operation, result, task_id)
            final_result = set(result)
        elif operation in ["Сравнение ID", "Автоматический парсинг"]:
            current_ids = set(result["current_ids"])
            added = set(result["added"])
            removed = set(result["removed"])

            store["last_ids"][url] = list(current_ids)
            save_store(store)

            final_result = (current_ids, added, removed)
        else:
            final_result = result

        if callback:
            await callback(query, None, final_result, url)

        log.info(f"✅ Задача {task_id} успешно завершена")

    except Exception as e:
        log.error(f"❌ Ошибка обработки успешного результата {task_id}: {e}")


async def handle_parsing_error(task_id: str, error: str, query, operation: str, is_auto: bool):
    """Обрабатывает ошибку парсинга"""
    log.error(f"❌ Задача {task_id} завершилась с ошибкой: {error}")

    if query and not is_auto:
        error_msg = error[:100] + "..." if len(error) > 100 else error
        try:
            await query.edit_message_text(
                f"❌ Ошибка выполнения\n"
                f"📋 {operation}\n"
                f"🚫 {error_msg}\n"
                f"🆔 ID: {task_id[:8]}"
            )
        except Exception as e:
            log.warning(f"⚠️ Ошибка отправки сообщения об ошибке: {e}")


async def queue_parsing_task(query, context: ContextTypes.DEFAULT_TYPE, data: str,
                             operation: str, callback, is_auto: bool = False):
    """Запускает парсинг как ФОНОВУЮ ЗАДАЧУ - НЕ БЛОКИРУЕТ БОТ"""
    idx = data.split("_", 1)[1]
    url_map = context.user_data.get(f"{data.split('_')[0]}_map", {})
    url = url_map.get(idx)

    if not url:
        await query.edit_message_text("❌ Сессия устарела. Начните заново.")
        return

    chat_id = str(query.from_user.id)
    task_id = f"{chat_id}_{int(time.time() * 1000000)}"

    log.info(f"🚀 ЗАПУСК ФОНОВОЙ ЗАДАЧИ {task_id}")
    log.info(f"   Chat ID: {chat_id}, URL: {url}")
    log.info(f"   Operation: {operation}, Auto: {is_auto}")

    # Уведомляем о запуске
    if query and not is_auto:
        from utils import subj_by_url
        await query.edit_message_text(
            f"🚀 Запуск парсинга...\n"
            f"📚 {subj_by_url(url)}\n"
            f"🆔 ID: {task_id[:8]}\n\n"
            f"🔄 Используйте другие функции"
        )

    # Запускаем как фоновую задачу - НЕ БЛОКИРУЕТ
    asyncio.create_task(start_parsing_background_task(
        task_id, chat_id, query, url, operation, callback, is_auto
    ))


async def get_queue_status() -> str:
    """Возвращает статус параллельных задач"""
    total_active = len(active_tasks)
    user_tasks = len([t for t in active_tasks.values() if not t.get("is_auto", False)])
    auto_tasks = len([t for t in active_tasks.values() if t.get("is_auto", False)])

    return (f"📊 Статус фоновых задач:\n"
            f"⚡ Всего активных: {total_active}\n"
            f"👤 Пользовательских: {user_tasks}\n"
            f"🤖 Автоматических: {auto_tasks}\n"
            f"💾 Память: {psutil.virtual_memory().percent:.1f}%\n"
            f"🖥️ CPU: {psutil.cpu_percent():.1f}%"
            )


async def process_queue_manager():
    """Менеджер фоновых задач - только очистка"""
    await init_executor()
    log.info("🚀 Менеджер фоновых задач запущен - БОТ НЕ БЛОКИРУЕТСЯ!")

    # Просто очищаем завершенные задачи
    while True:
        try:
            completed_tasks = [tid for tid, future in running_futures.items() if future.done()]
            for task_id in completed_tasks:
                if task_id in running_futures:
                    del running_futures[task_id]
                if task_id in active_tasks:
                    log.info(f"🧹 Очищена завершенная задача: {task_id}")
                    del active_tasks[task_id]

            await asyncio.sleep(10)
        except Exception as e:
            log.error(f"❌ Ошибка в менеджере: {e}")
            await asyncio.sleep(5)
