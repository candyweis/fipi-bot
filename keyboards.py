# -*- coding: utf-8 -*-
"""
Клавиатуры для Telegram бота - С выбором кэшированных результатов
"""
from telegram import ReplyKeyboardMarkup, KeyboardButton
from config import OGE_SUBJECT_LIST, EGE_SUBJECT_LIST


def kb_main_reply() -> ReplyKeyboardMarkup:
    """Главное меню - Reply клавиатура"""
    keyboard = [
        ["📚 Подписки", "📊 Количество заданий"],
        ["🆔 Файл всех ID", "🔄 Сравнить ID"],
        ["❌ Отписаться", "📋 Мои подписки"],
        ["ℹ️ Статус очереди"]
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите действие..."
    )


def kb_subjects_reply(exam_type: str) -> ReplyKeyboardMarkup:
    """Клавиатура выбора предметов - Reply"""
    subjects = OGE_SUBJECT_LIST if exam_type == "oge" else EGE_SUBJECT_LIST
    keyboard = []

    # Группируем предметы по 2 в строке
    for i in range(0, len(subjects), 2):
        row = []
        for j in range(i, min(i + 2, len(subjects))):
            name, _ = subjects[j]
            prefix = "ОГЭ" if exam_type == "oge" else "ЕГЭ"
            row.append(f"{prefix} {name}")
        keyboard.append(row)

    keyboard.append(["⬅ Назад в меню"])

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )


def kb_user_subjects_reply(subjects_urls: list, action: str) -> ReplyKeyboardMarkup:
    """Клавиатура с предметами пользователя - Reply"""
    from utils import subj_by_url

    keyboard = []

    # Группируем предметы по 2 в строке
    for i in range(0, len(subjects_urls), 2):
        row = []
        for j in range(i, min(i + 2, len(subjects_urls))):
            subject_name = subj_by_url(subjects_urls[j])
            row.append(subject_name)
        keyboard.append(row)

    keyboard.append(["⬅ Назад в меню"])

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )


def kb_subscriptions_menu_reply() -> ReplyKeyboardMarkup:
    """Меню подписок - Reply"""
    keyboard = [
        ["Подписаться на ОГЭ", "Подписаться на ЕГЭ"],
        ["⬅ Назад в меню"]
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )


def kb_cached_result_choice() -> ReplyKeyboardMarkup:
    """Клавиатура выбора между кэшированным результатом и новым парсингом"""
    keyboard = [
        ["📁 Использовать готовый результат"],
        ["🔄 Запустить новый парсинг"],
        ["⬅ Назад в меню"]
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )
