# -*- coding: utf-8 -*-
"""
Обработчики команд и сообщений Telegram - С редактированием сообщений
"""
import os
import asyncio
import logging
from datetime import datetime
from telegram import Update, Message
from telegram.ext import ContextTypes, ApplicationHandlerStop

from keyboards import (kb_main_reply, kb_subjects_reply, kb_user_subjects_reply,
                       kb_subscriptions_menu_reply, kb_cached_result_choice)
from database import (store, save_store, get_recent_parsing, save_parsing_result,
                      clean_old_parsing_cache)
from utils import subj_by_url, get_current_count, split_message, send_changes_file
from queue_manager import queue_parsing_task, get_queue_status  # Убраны last_parsing_*
from config import OGE_SUBJECT_LIST, EGE_SUBJECT_LIST, OGE_SUBJECTS, EGE_SUBJECTS

log = logging.getLogger("FIPI-Bot")


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    clean_old_parsing_cache()

    await update.message.reply_text(
        "🤖 Добро пожаловать в ФИПИ-бот!\n\n"
        "Выберите действие с помощью кнопок ниже:",
        reply_markup=kb_main_reply()
    )


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /status - показывает статус очереди"""
    status = await get_queue_status()
    await update.message.reply_text(status, reply_markup=kb_main_reply())


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений (Reply кнопки)"""
    message: Message = update.message
    text = message.text
    chat_id = str(message.from_user.id)

    log.info(f"Text message: '{text}' from chat_id: {chat_id}")

    # Обработка выбора кэшированного результата
    if context.user_data.get("waiting_for_cache_choice"):
        await handle_cache_choice(message, context, text)
        return

    # ПРИОРИТЕТ: Сначала проверяем, ждем ли мы выбор предмета от пользователя
    if context.user_data.get("waiting_for_subject"):
        await handle_user_subject_action(message, context, text)
        return

    # Назад в меню
    if text == "⬅ Назад в меню":
        context.user_data.clear()
        await message.reply_text("🏠 Главное меню:", reply_markup=kb_main_reply())
        return

    # Главное меню
    if text == "📚 Подписки":
        await show_subscriptions_menu(message, context)
    elif text == "📊 Количество заданий":
        await show_task_counts(message, context)
    elif text == "🆔 Файл всех ID":
        await show_ids_menu(message, context)
    elif text == "🔄 Сравнить ID":
        await show_compare_menu(message, context)
    elif text == "❌ Отписаться":
        await show_unsubscribe_menu(message, context)
    elif text == "📋 Мои подписки":
        await show_my_subscriptions(message, context)
    elif text == "ℹ️ Статус очереди":
        status = await get_queue_status()
        await message.reply_text(status, reply_markup=kb_main_reply())

    # Подписки на ОГЭ/ЕГЭ
    elif text.startswith("Подписаться на ОГЭ"):
        await message.reply_text(
            "📚 Выберите предмет ОГЭ:",
            reply_markup=kb_subjects_reply("oge")
        )
    elif text.startswith("Подписаться на ЕГЭ"):
        await message.reply_text(
            "📚 Выберите предмет ЕГЭ:",
            reply_markup=kb_subjects_reply("ege")
        )

    # Обработка выбора предметов для ПОДПИСКИ
    elif text.startswith("ОГЭ ") or text.startswith("ЕГЭ "):
        await handle_subject_selection(message, context, text)

    else:
        await message.reply_text(
            "❓ Не понимаю эту команду. Используйте кнопки меню:",
            reply_markup=kb_main_reply()
        )


async def handle_cache_choice(message: Message, context: ContextTypes.DEFAULT_TYPE, text: str):
    """Обрабатывает выбор между кэшированным результатом и новым парсингом"""
    if text == "⬅ Назад в меню":
        context.user_data.clear()
        await message.reply_text("🏠 Главное меню:", reply_markup=kb_main_reply())
        return

    cached_data = context.user_data.get("cached_result")
    operation = context.user_data.get("pending_operation")
    url = context.user_data.get("pending_url")

    if not cached_data or not operation or not url:
        await message.reply_text("❌ Ошибка данных. Попробуйте снова.", reply_markup=kb_main_reply())
        context.user_data.clear()
        return

    if text == "📁 Использовать готовый результат":
        if operation == "Создание файла ID":
            result = set(cached_data["result"])
            await send_cached_ids_file(message, result, url, cached_data["timestamp"])
        elif operation == "Сравнение ID":
            await message.reply_text(
                "⚠️ Для сравнения ID нужен свежий парсинг.\nЗапускаю новый парсинг...",
                reply_markup=kb_main_reply()
            )
            await start_new_parsing(message, context, url, operation)

        context.user_data.clear()

    elif text == "🔄 Запустить новый парсинг":
        await start_new_parsing(message, context, url, operation)
        context.user_data.clear()

    else:
        await message.reply_text(
            "❓ Выберите один из вариантов:",
            reply_markup=kb_cached_result_choice()
        )


async def send_cached_ids_file(message: Message, ids: set, url: str, timestamp: str):
    """Отправляет кэшированный файл с ID"""
    fname = f"cached_ids_{url.split('=')[-1]}_{timestamp.replace(':', '-').replace('.', '_')}.txt"
    with open(fname, "w", encoding="utf-8") as f:
        for t in sorted(ids):
            f.write(t + "\n")

    try:
        dt = datetime.fromisoformat(timestamp)
        time_str = dt.strftime("%d.%m.%Y %H:%M")
    except:
        time_str = timestamp

    with open(fname, "rb") as f:
        await message.reply_document(
            f, filename=fname,
            caption=f"📁 {subj_by_url(url)}\n🕒 Парсинг от {time_str}\n🆔 Всего {len(ids)} ID"
        )

    await message.reply_text("✅ Готовый файл отправлен!", reply_markup=kb_main_reply())

    try:
        os.remove(fname)
    except:
        pass


async def start_new_parsing(message: Message, context: ContextTypes.DEFAULT_TYPE, url: str, operation: str):
    """Запускает новый парсинг с редактированием сообщения"""
    # Отправляем начальное сообщение
    status_message = await message.reply_text("⏳ Подготовка к парсингу...")

    class EditableQuery:
        def __init__(self, message, status_message):
            self.message = message
            self.status_message = status_message
            self.from_user = message.from_user

        async def edit_message_text(self, text, reply_markup=None):
            try:
                await self.status_message.edit_text(text)
            except Exception as e:
                log.warning(f"Ошибка редактирования сообщения: {e}")
                # Если не удалось отредактировать, отправляем новое
                await self.message.reply_text(text)

    editable_query = EditableQuery(message, status_message)

    if operation == "Создание файла ID":
        context.user_data["ids_map"] = {"0": url}
        await queue_parsing_task(editable_query, context, "ids_0", operation, send_ids_file_result)
    elif operation == "Сравнение ID":
        context.user_data["cmp_map"] = {"0": url}
        await queue_parsing_task(editable_query, context, "cmp_0", operation, compare_ids_now_result)


async def show_subscriptions_menu(message: Message, context: ContextTypes.DEFAULT_TYPE):
    """Показывает меню подписок"""
    await message.reply_text(
        "📚 Выберите тип экзамена:",
        reply_markup=kb_subscriptions_menu_reply()
    )


async def handle_subject_selection(message: Message, context: ContextTypes.DEFAULT_TYPE, text: str):
    """Обрабатывает выбор предмета для ПОДПИСКИ"""
    chat_id = str(message.from_user.id)

    log.info(f"Обработка подписки для: {text}")

    if text.startswith("ОГЭ "):
        exam_type = "oge"
        subject_name = text[4:]
        subjects_dict = OGE_SUBJECTS
    elif text.startswith("ЕГЭ "):
        exam_type = "ege"
        subject_name = text[4:]
        subjects_dict = EGE_SUBJECTS
    else:
        await message.reply_text("❌ Неверный формат. Выберите из меню.", reply_markup=kb_main_reply())
        return

    url = subjects_dict.get(subject_name)
    if not url:
        await message.reply_text("❌ Предмет не найден. Выберите из списка.", reply_markup=kb_main_reply())
        return

    subs = store["subscriptions"].setdefault(chat_id, [])
    if url in subs:
        await message.reply_text(
            f"✅ Вы уже подписаны на {text}",
            reply_markup=kb_main_reply()
        )
    else:
        subs.append(url)
        save_store(store)
        await message.reply_text(
            f"✅ Подписка активирована: {text}",
            reply_markup=kb_main_reply()
        )


async def show_my_subscriptions(message: Message, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список подписок пользователя"""
    chat_id = str(message.from_user.id)
    subs = store["subscriptions"].get(chat_id, [])

    if not subs:
        await message.reply_text(
            "📭 У вас нет активных подписок.",
            reply_markup=kb_main_reply()
        )
    else:
        text_lines = ["📋 Ваши подписки:"]
        for i, url in enumerate(subs, 1):
            text_lines.append(f"{i}. {subj_by_url(url)}")

        await message.reply_text(
            "\n".join(text_lines),
            reply_markup=kb_main_reply()
        )


async def show_task_counts(message: Message, context: ContextTypes.DEFAULT_TYPE):
    """Показывает текущее количество заданий по подпискам"""
    chat_id = str(message.from_user.id)
    subs = store["subscriptions"].get(chat_id, [])

    if not subs:
        await message.reply_text(
            "📭 У вас нет подписок.",
            reply_markup=kb_main_reply()
        )
        return

    # Отправляем сообщение которое будем редактировать
    msg = await message.reply_text("📊 Получение данных...")

    lines = ["📊 Текущее количество заданий:"]
    for i, url in enumerate(subs, 1):
        try:
            # Обновляем прогресс
            await msg.edit_text(f"📊 Получение данных... ({i}/{len(subs)})")

            cnt = await asyncio.get_event_loop().run_in_executor(None, get_current_count, url)
            lines.append(f"• {subj_by_url(url)}: {cnt if cnt is not None else 'не получено'}")
        except Exception as e:
            log.error(f"Ошибка получения количества для {url}: {e}")
            lines.append(f"• {subj_by_url(url)}: ошибка")

    # Финальное обновление
    await msg.edit_text("\n".join(lines))
    await message.reply_text("✅ Данные обновлены", reply_markup=kb_main_reply())


async def show_ids_menu(message: Message, context: ContextTypes.DEFAULT_TYPE):
    """Показывает меню для создания файла ID"""
    chat_id = str(message.from_user.id)
    subs = store["subscriptions"].get(chat_id, [])

    if not subs:
        await message.reply_text(
            "📭 У вас нет подписок.",
            reply_markup=kb_main_reply()
        )
        return

    context.user_data["waiting_for_subject"] = "ids"
    context.user_data["current_operation"] = "Создание файла ID"

    await message.reply_text(
        "🆔 Выберите предмет для создания файла ID:",
        reply_markup=kb_user_subjects_reply(subs, "ids")
    )


async def show_compare_menu(message: Message, context: ContextTypes.DEFAULT_TYPE):
    """Показывает меню для сравнения ID"""
    chat_id = str(message.from_user.id)
    subs = store["subscriptions"].get(chat_id, [])

    if not subs:
        await message.reply_text(
            "📭 У вас нет подписок.",
            reply_markup=kb_main_reply()
        )
        return

    context.user_data["waiting_for_subject"] = "compare"
    context.user_data["current_operation"] = "Сравнение ID"
    await message.reply_text(
        "🔄 Выберите предмет для сравнения ID:",
        reply_markup=kb_user_subjects_reply(subs, "compare")
    )


async def show_unsubscribe_menu(message: Message, context: ContextTypes.DEFAULT_TYPE):
    """Показывает меню для отписки"""
    chat_id = str(message.from_user.id)
    subs = store["subscriptions"].get(chat_id, [])

    if not subs:
        await message.reply_text(
            "📭 У вас нет подписок.",
            reply_markup=kb_main_reply()
        )
        return

    context.user_data["waiting_for_subject"] = "unsubscribe"
    await message.reply_text(
        "❌ Выберите предмет для отписки:",
        reply_markup=kb_user_subjects_reply(subs, "unsubscribe")
    )


async def handle_user_subject_action(message: Message, context: ContextTypes.DEFAULT_TYPE, text: str):
    """Обрабатывает действия с предметами пользователя"""
    action = context.user_data.get("waiting_for_subject")
    operation = context.user_data.get("current_operation")

    if text == "⬅ Назад в меню":
        context.user_data.clear()
        await message.reply_text("🏠 Главное меню:", reply_markup=kb_main_reply())
        return

    chat_id = str(message.from_user.id)
    subs = store["subscriptions"].get(chat_id, [])

    url = None
    for sub_url in subs:
        if subj_by_url(sub_url) == text:
            url = sub_url
            break

    if not url:
        await message.reply_text(
            "❌ Предмет не найден. Выберите из списка.",
            reply_markup=kb_user_subjects_reply(subs, action)
        )
        return

    context.user_data.pop("waiting_for_subject", None)

    if action == "unsubscribe":
        await process_unsubscribe(message, context, url)
        return

    # Проверяем кэш для операций парсинга
    if operation in ["Создание файла ID", "Сравнение ID"]:
        cached = get_recent_parsing(url, operation)
        if cached:
            try:
                dt = datetime.fromisoformat(cached["timestamp"])
                time_str = dt.strftime("%d.%m.%Y %H:%M")
            except:
                time_str = cached["timestamp"]

            context.user_data["cached_result"] = cached
            context.user_data["pending_operation"] = operation
            context.user_data["pending_url"] = url
            context.user_data["waiting_for_cache_choice"] = True

            await message.reply_text(
                f"📁 Найден недавний результат парсинга!\n\n"
                f"📚 {subj_by_url(url)}\n"
                f"🕒 Время парсинга: {time_str}\n"
                f"📋 Операция: {operation}\n"
                f"🆔 Найдено ID: {len(cached['result'])}\n\n"
                f"Что хотите сделать?",
                reply_markup=kb_cached_result_choice()
            )
            return

    # Нет кэша - запускаем новый парсинг
    if action == "ids":
        await start_ids_parsing(message, context, url)
    elif action == "compare":
        await start_compare_parsing(message, context, url)


async def start_ids_parsing(message: Message, context: ContextTypes.DEFAULT_TYPE, url: str):
    """Запускает парсинг ID"""
    await start_new_parsing(message, context, url, "Создание файла ID")


async def start_compare_parsing(message: Message, context: ContextTypes.DEFAULT_TYPE, url: str):
    """Запускает сравнение ID"""
    await start_new_parsing(message, context, url, "Сравнение ID")


async def process_unsubscribe(message: Message, context: ContextTypes.DEFAULT_TYPE, url: str):
    """Обрабатывает отписку"""
    chat_id = str(message.from_user.id)
    subs = store["subscriptions"].get(chat_id, [])

    if url in subs:
        subs.remove(url)
        save_store(store)
        await message.reply_text(
            f"✅ Вы отписались от: {subj_by_url(url)}",
            reply_markup=kb_main_reply()
        )
    else:
        await message.reply_text(
            "❌ Вы уже не подписаны на этот предмет.",
            reply_markup=kb_main_reply()
        )


async def send_ids_file_result(query, context: ContextTypes.DEFAULT_TYPE, ids: set, url: str):
    """Отправляет файл с ID заданий и сохраняет в кэш"""
    fname = f"ids_{url.split('=')[-1]}.txt"
    with open(fname, "w", encoding="utf-8") as f:
        for t in sorted(ids):
            f.write(t + "\n")

    # Сохраняем в кэш
    save_parsing_result(url, "Создание файла ID", ids, str(query.from_user.id))

    # Обновляем статусное сообщение
    await query.edit_message_text("✅ Парсинг завершен! Отправляю файл...")

    with open(fname, "rb") as f:
        await query.message.reply_document(
            f, filename=fname,
            caption=f"🆔 {subj_by_url(url)} • всего {len(ids)} ID"
        )

    await query.message.reply_text("✅ Файл отправлен!", reply_markup=kb_main_reply())

    try:
        os.remove(fname)
    except:
        pass


async def compare_ids_now_result(query, context: ContextTypes.DEFAULT_TYPE, result: tuple, url: str):
    """Обрабатывает результат сравнения ID"""
    current_ids, added, removed = result
    timestamp = datetime.now().isoformat()

    if not added and not removed:
        await query.edit_message_text("🔄 Парсинг завершен. Изменений не найдено.")
        await query.message.reply_text(
            "🔄 Изменений нет.",
            reply_markup=kb_main_reply()
        )
    else:
        await query.edit_message_text("✅ Парсинг завершен! Найдены изменения...")

        txt_lines = ["🔄 Изменения найдены:"]
        if added:
            txt_lines.append(f"➕ Добавлены ({len(added)}): " + ", ".join(sorted(list(added)[:10])))
            if len(added) > 10:
                txt_lines.append(f"   ... и ещё {len(added) - 10}")
        if removed:
            txt_lines.append(f"➖ Удалены ({len(removed)}): " + ", ".join(sorted(list(removed)[:10])))
            if len(removed) > 10:
                txt_lines.append(f"   ... и ещё {len(removed) - 10}")

        txt = "\n".join(txt_lines)

        messages = split_message(txt)
        for msg in messages:
            await query.message.reply_text(msg)

        await send_changes_file(query, context, url, added, removed, timestamp)
        await query.message.reply_text("✅ Результаты отправлены!", reply_markup=kb_main_reply())


async def on_shutdown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очищает ресурсы при остановке бота."""
    log.info("Остановка бота, очистка ресурсов")
    from queue_manager import shutdown_executor
    await shutdown_executor()
    raise ApplicationHandlerStop


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    log.error(f"Ошибка: {context.error}")
