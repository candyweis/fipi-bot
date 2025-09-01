# -*- coding: utf-8 -*-
"""
Конфигурация и константы для ФИПИ-бота
"""

BOT_TOKEN = "7238087192:AAF_v9R4jS_O2dZ8tRqG6wjNbEk75GUSrkA"

DATA_FILE = "bot_data.json"
CHECK_INTERVAL = 60  # Проверка каждую минуту
TELEGRAM_MAX_MESSAGE_LENGTH = 4096
INITIAL_RETRY_DELAY = 5
RETRY_DELAY_MULTIPLIER = 2
MAX_WEBDRIVERS = 4
PARSING_TIMEOUT = 18000  # 30 минут максимум на парсинг

# Настройки параллельного парсинга
MAX_CONCURRENT_PARSING = 30  # Максимум 3 парсинга одновременно
MAX_CONCURRENT_AUTO_PARSING = 25  # Максимум 2 автоматических парсинга одновременно
MEMORY_LIMIT_PERCENT = 85  # Если память > 85%, не запускать новые парсинги
CPU_LIMIT_PERCENT = 90  # Если CPU > 90%, не запускать новые парсинги

OGE_SUBJECTS = {
    "Английский язык": "https://oge.fipi.ru/bank/index.php?proj=8BBD5C99F37898B6402964AB11955663",
    "Биология":         "https://oge.fipi.ru/bank/index.php?proj=0E1FA4229923A5CE4FC368155127ED90",
    "География":        "https://oge.fipi.ru/bank/index.php?proj=0FA4DA9E3AE2BA1547B75F0B08EF6445",
    "Информатика":      "https://oge.fipi.ru/bank/index.php?proj=74676951F093A0754D74F2D6E7955F06",
    "История":          "https://oge.fipi.ru/bank/index.php?proj=3CBBE97571208D9140697A6C2ABE91A0",
    "Литература":       "https://oge.fipi.ru/bank/index.php?proj=6B2CD4C77304B2A3478E5A5B61F6899A",
    "Математика":       "https://oge.fipi.ru/bank/index.php?proj=DE0E276E497AB3784C3FC4CC20248DC0",
    "Обществознание":   "https://oge.fipi.ru/bank/index.php?proj=AE63AB28A2D28E194A286FA5A8EB9A78",
    "Русский язык":     "https://oge.fipi.ru/bank/index.php?proj=2F5EE3B12FE2A0EA40B06BF61A015416",
    "Физика":           "https://oge.fipi.ru/bank/index.php?proj=B24AFED7DE6AB5BC461219556CCA4F9B",
    "Химия":            "https://oge.fipi.ru/bank/index.php?proj=33B3A93C5A6599124B04FB95616C835B"
}

EGE_SUBJECTS = {
    "Английский язык":              "https://ege.fipi.ru/bank/index.php?proj=4B53A6CB75B0B5E1427E596EB4931A2A",
    "Биология":                      "https://ege.fipi.ru/bank/index.php?proj=CA9D848A31849ED149D382C32A7A2BE4",
    "География":                     "https://ege.fipi.ru/bank/index.php?proj=20E79180061DB32845C11FC7BD87C7C8",
    "Информатика и ИКТ":             "https://ege.fipi.ru/bank/index.php?proj=B9ACA5BBB2E19E434CD6BEC25284C67F",
    "История":                       "https://ege.fipi.ru/bank/index.php?proj=068A227D253BA6C04D0C832387FD0D89",
    "Литература":                    "https://ege.fipi.ru/bank/index.php?proj=4F431E63B9C9B25246F00AD7B5253996",
    "Математика. Базовый уровень":   "https://ege.fipi.ru/bank/index.php?proj=E040A72A1A3DABA14C90C97E0B6EE7DC",
    "Математика. Профильный уровень": "https://ege.fipi.ru/bank/index.php?proj=AC437B34557F88EA4115D2F374B0A07B",
    "Обществознание":                "https://ege.fipi.ru/bank/index.php?proj=756DF168F63F9A6341711C61AA5EC578",
    "Русский язык":                  "https://ege.fipi.ru/bank/index.php?proj=AF0ED3F2557F8FFC4C06F80B6803FD26",
    "Физика":                        "https://ege.fipi.ru/bank/index.php?proj=BA1F39653304A5B041B656915DC36B38",
    "Химия":                         "https://ege.fipi.ru/bank/index.php?proj=EA45D8517ABEB35140D0D83E76F14A41"
}

OGE_SUBJECT_LIST = list(OGE_SUBJECTS.items())
EGE_SUBJECT_LIST = list(EGE_SUBJECTS.items())
