# -*- coding: utf-8 -*-
"""
Периодические задачи бота - Автоматический парсинг при изменениях
"""
import os
import asyncio
import logging
from datetime import datetime, timedelta
from telegram.ext import ContextTypes
from parser import TaskIdExtractor
from database import store, save_store, save_parsing_result
from utils import subj_by_url, get_current_count, split_message
from keyboards import kb_main_reply

log = logging.getLogger("FIPI-Bot")

# Глобальная переменная для отслеживания активных парсингов
active_auto_parsing = set()

async def periodic_check(context: ContextTypes.DEFAULT_TYPE):
    """Периодическая проверка изменений каждую минуту"""
    log.info("🔍 Начало автоматической проверки...")
    # Получаем все уникальные URL из подписок
    all_urls = set()
    for user_urls in store["subscriptions"].values():
        all_urls.update(user_urls)
    if not all_urls:
        log.info("📭 Нет подписок для проверки")
        return
    log.info(f"🔍 Проверяю {len(all_urls)} предметов...")
    for url in all_urls:
        try:
            await check_url_changes(context, url)
        except Exception as e:
            log.error(f"❌ Ошибка проверки URL {url}: {e}")
    log.info("✅ Автоматическая проверка завершена")

async def check_url_changes(context: ContextTypes.DEFAULT_TYPE, url: str):
    """Проверяет изменения для конкретного URL"""
    subject_name = subj_by_url(url)
    try:
        log.info(f"📊 Проверяю количество заданий для {subject_name}")
        try:
            current_count = await asyncio.to_thread(get_current_count, url)
        except AttributeError:
            loop = asyncio.get_event_loop()
            current_count = await loop.run_in_executor(None, get_current_count, url)
        if current_count is None:
            log.warning(f"⚠️ Не удалось получить количество для {subject_name}")
            return
        previous_count = store["last_counts"].get(url)
        if previous_count is None:
            log.info(f"📝 Первая проверка {subject_name}: {current_count} заданий")
            store["last_counts"][url] = current_count
            save_store(store)
            return
        if previous_count != current_count:
            log.info(f"🚨 ИЗМЕНЕНИЕ ОБНАРУЖЕНО! {subject_name}: {previous_count} → {current_count}")
            if url in active_auto_parsing:
                log.info(f"⏳ Парсинг для {subject_name} уже активен, пропускаю")
                return
            active_auto_parsing.add(url)
            try:
                await notify_quantity_change(context, url, previous_count, current_count)
                await start_automatic_parsing(context, url, current_count)
            finally:
                active_auto_parsing.discard(url)
        else:
            log.debug(f"📊 {subject_name}: количество не изменилось ({current_count})")
    except Exception as e:
        log.error(f"❌ Ошибка проверки изменений для {subject_name}: {e}")

async def notify_quantity_change(context: ContextTypes.DEFAULT_TYPE, url: str,
                                 old_count: int, new_count: int):
    """Уведомляет пользователей об изменении количества заданий"""
    subject_name = subj_by_url(url)
    subscribers = []
    for chat_id, urls in store["subscriptions"].items():
        if url in urls:
            subscribers.append(chat_id)
    if not subscribers:
        return
    change_type = "📈 Увеличилось" if new_count > old_count else "📉 Уменьшилось"
    difference = abs(new_count - old_count)
    message = (f"🔔 Автоматическое обнаружение изменений!\n\n"
               f"📚 {subject_name}\n"
               f"{change_type} на {difference}\n"
               f"📊 Было: {old_count} → Стало: {new_count}\n\n"
               f"🤖 Автоматически запускаю парсинг для поиска изменений...")
    log.info(f"📢 Отправка уведомлений {len(subscribers)} подписчикам")
    for chat_id in subscribers:
        try:
            await context.bot.send_message(
                chat_id=int(chat_id),
                text=message,
                reply_markup=kb_main_reply()
            )
        except Exception as e:
            log.error(f"❌ Ошибка отправки уведомления пользователю {chat_id}: {e}")

async def start_automatic_parsing(context: ContextTypes.DEFAULT_TYPE, url: str, current_count: int):
    """Запускает автоматический парсинг при изменении количества"""
    from queue_manager import queue_parsing_task
    subject_name = subj_by_url(url)
    log.info(f"🚀 Запуск автоматического парсинга для {subject_name}")
    class AutoQuery:
        def __init__(self):
            self.from_user = type('User', (), {'id': 'auto'})()
        async def edit_message_text(self, text, reply_markup=None):
            log.info(f"🤖 Автопарсинг: {text}")
    auto_query = AutoQuery()
    fake_context = type('Context', (), {
        'user_data': {'cmp_map': {'0': url}}
    })()
    try:
        await queue_parsing_task(
            auto_query, fake_context, "cmp_0",
            "Автоматический парсинг",
            lambda q, c, r, u: auto_parsing_callback(q, c, r, u, context),
            is_auto=True
        )
    except Exception as e:
        log.error(f"❌ Ошибка запуска автоматического парсинга для {subject_name}: {e}")

async def auto_parsing_callback(query, context_unused, result, url, bot_context):
    """Callback для автоматического парсинга"""
    try:
        current_ids, added, removed = result
        timestamp = datetime.now().isoformat()
        current_count = len(current_ids)
        store["last_counts"][url] = current_count
        save_store(store)
        if added or removed:
            await notify_id_changes(bot_context, url, added, removed, len(current_ids))
        else:
            await notify_no_id_changes(bot_context, url, len(current_ids))
    except Exception as e:
        log.error(f"❌ Ошибка в callback автопарсинга для {url}: {e}")

async def notify_id_changes(context: ContextTypes.DEFAULT_TYPE, url: str,
                           added: set, removed: set, total_count: int):
    """Уведомляет о найденных изменениях ID"""
    subject_name = subj_by_url(url)
    timestamp = datetime.now().isoformat()
    subscribers = []
    for chat_id, urls in store["subscriptions"].items():
        if url in urls:
            subscribers.append(chat_id)
    if not subscribers:
        return
    change_parts = []
    if added:
        change_parts.append(f"➕ Добавлено: {len(added)} ID")
    if removed:
        change_parts.append(f"➖ Удалено: {len(removed)} ID")
    change_text = "\n".join(change_parts)
    main_message = (f"✅ Автоматический парсинг завершен!\n\n"
                    f"📚 {subject_name}\n"
                    f"🆔 Всего ID: {total_count}\n\n"
                    f"🔍 НАЙДЕНЫ ИЗМЕНЕНИЯ:\n{change_text}\n\n"
                    f"📄 Подробности в файле ↓")
    log.info(f"📊 Отправка результатов изменений {len(subscribers)} подписчикам")
    for chat_id in subscribers:
        try:
            messages = split_message(main_message)
            for msg in messages:
                await context.bot.send_message(
                    chat_id=int(chat_id),
                    text=msg,
                    reply_markup=kb_main_reply()
                )
            await send_auto_changes_file(context, chat_id, url, added, removed, timestamp)
        except Exception as e:
            log.error(f"❌ Ошибка отправки результатов пользователю {chat_id}: {e}")

async def notify_no_id_changes(context: ContextTypes.DEFAULT_TYPE, url: str, total_count: int):
    """Уведомляет об отсутствии изменений ID"""
    subject_name = subj_by_url(url)
    subscribers = []
    for chat_id, urls in store["subscriptions"].items():
        if url in urls:
            subscribers.append(chat_id)
    if not subscribers:
        return
    message = (f"✅ Автоматический парсинг завершен!\n\n"
               f"📚 {subject_name}\n"
               f"🆔 Всего ID: {total_count}\n\n"
               f"ℹ️ Количество заданий изменилось, но состав ID остался прежним")
    for chat_id in subscribers:
        try:
            await context.bot.send_message(
                chat_id=int(chat_id),
                text=message,
                reply_markup=kb_main_reply()
            )
        except Exception as e:
            log.error(f"❌ Ошибка отправки уведомления {chat_id}: {e}")

async def send_auto_changes_file(context: ContextTypes.DEFAULT_TYPE, chat_id: str,
                                url: str, added: set, removed: set, timestamp: str):
    """Создает и отправляет файл с изменениями ID"""
    try:
        subject_name = subj_by_url(url)
        safe_timestamp = timestamp.replace(':', '-').replace('.', '_')
        filename = f"auto_changes_{url.split('=')[-1]}_{safe_timestamp}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"🤖 АВТОМАТИЧЕСКОЕ ОБНАРУЖЕНИЕ ИЗМЕНЕНИЙ\n")
            f.write(f"Предмет: {subject_name}\n")
            f.write(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"=" * 50 + "\n\n")
            if added:
                f.write(f"➕ ДОБАВЛЕНЫ ID ({len(added)}):\n")
                f.write("-" * 30 + "\n")
                for task_id in sorted(added):
                    f.write(f"{task_id}\n")
                f.write("\n")
            if removed:
                f.write(f"➖ УДАЛЕНЫ ID ({len(removed)}):\n")
                f.write("-" * 30 + "\n")
                for task_id in sorted(removed):
                    f.write(f"{task_id}\n")
                f.write("\n")
            f.write(f"📊 СТАТИСТИКА:\n")
            f.write(f"Добавлено: {len(added)} ID\n")
            f.write(f"Удалено: {len(removed)} ID\n")
            f.write(f"Общее изменение: {len(added) - len(removed):+d} ID\n")
        with open(filename, "rb") as f:
            await context.bot.send_document(
                chat_id=int(chat_id),
                document=f,
                filename=filename,
                caption=f"🤖 Автоматическое обнаружение изменений\n📚 {subject_name}"
            )
        try:
            os.remove(filename)
        except Exception as e:
            log.warning(f"⚠️ Не удалось удалить файл {filename}: {e}")
    except Exception as e:
        log.error(f"❌ Ошибка создания файла изменений для {chat_id}: {e}")

async def cleanup_old_data():
    """Очищает устаревшие данные"""
    try:
        cutoff_date = datetime.now() - timedelta(days=30)
        cleaned_count = 0
        for url in list(store.get("historical_ids", {}).keys()):
            history = store["historical_ids"][url]
            if history:
                # Сортируем по дате (новые сверху)
                sorted_history = sorted(history, key=lambda x: datetime.fromisoformat(x["timestamp"]), reverse=True)
                # Сохраняем последний (самый свежий)
                filtered_history = [sorted_history[0]]
                # Добавляем остальные, если не старше cutoff
                for record in sorted_history[1:]:
                    if datetime.fromisoformat(record["timestamp"]) > cutoff_date:
                        filtered_history.append(record)
                if len(filtered_history) != len(history):
                    store["historical_ids"][url] = filtered_history
                    cleaned_count += len(history) - len(filtered_history)
        from database import clean_old_parsing_cache
        clean_old_parsing_cache()
        empty_subscriptions = []
        for chat_id, urls in store.get("subscriptions", {}).items():
            if not urls:
                empty_subscriptions.append(chat_id)
        for chat_id in empty_subscriptions:
            del store["subscriptions"][chat_id]
        if empty_subscriptions:
            log.info(f"🧹 Удалены пустые подписки: {len(empty_subscriptions)}")
        save_store(store)
        log.info(f"🧹 Очистка завершена: удалено {cleaned_count} устаревших записей")
    except Exception as e:
        log.error(f"❌ Ошибка очистки данных: {e}")

async def daily_cleanup(context: ContextTypes.DEFAULT_TYPE):
    """Ежедневная очистка устаревших данных"""
    log.info("🧹 Запуск ежедневной очистки данных")
    try:
        await cleanup_old_data()
        temp_files_removed = 0
        for filename in os.listdir("."):
            if (filename.startswith("progress_") or
                filename.startswith("auto_changes_") or
                filename.startswith("cached_ids_") or
                filename.startswith("ids_") or
                filename.startswith("changes_")):
                try:
                    file_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(filename))
                    if file_age.total_seconds() > 3600:  # Старше часа
                        os.remove(filename)
                        temp_files_removed += 1
                except Exception as e:
                    log.warning(f"⚠️ Не удалось удалить временный файл {filename}: {e}")
        if temp_files_removed > 0:
            log.info(f"🧹 Удалено временных файлов: {temp_files_removed}")
        total_subscriptions = sum(len(urls) for urls in store.get("subscriptions", {}).values())
        total_users = len(store.get("subscriptions", {}))
        log.info(f"📊 Статистика после очистки:")
        log.info(f" 👥 Пользователей: {total_users}")
        log.info(f" 📚 Подписок: {total_subscriptions}")
        log.info(f" 🗂️ URLs в истории: {len(store.get('historical_ids', {}))}")
        log.info(f" 💾 Размер кэша: {len(store.get('recent_parsing', {}))}")
    except Exception as e:
        log.error(f"❌ Ошибка ежедневной очистки: {e}")
