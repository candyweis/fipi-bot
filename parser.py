# -*- coding: utf-8 -*-
"""
Парсер ID заданий с ФИПИ - СЕРВЕРНАЯ ВЕРСИЯ
"""
import time
import logging
import os
import shutil
from typing import Set
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from database import store, save_store
from config import INITIAL_RETRY_DELAY, RETRY_DELAY_MULTIPLIER, PARSING_TIMEOUT

log = logging.getLogger("FIPI-Bot")


class ServerTaskIdExtractor:
    """WebDriver для серверного окружения с улучшенной стабильностью"""

    def __init__(self, timeout: int = 15, max_reloads: int = 2):
        self.timeout = timeout
        self.max_reloads = max_reloads
        self.driver = None
        self.start_time = None
        self.driver_pid = None
        log.info("Создан ServerTaskIdExtractor для серверного окружения")

    # Замените метод _init_driver в parser.py:

    def _init_driver(self):
        """Инициализация WebDriver с системным ChromeDriver"""
        try:
            # Проверяем доступность Chrome
            chrome_path = shutil.which('google-chrome') or shutil.which('chromium-browser')
            if not chrome_path:
                raise Exception("Chrome/Chromium не найден в системе")

            log.info(f"Используется Chrome: {chrome_path}")

            # Серверные опции Chrome
            options = Options()

            # ОБЯЗАТЕЛЬНЫЕ опции для сервера
            options.add_argument("--headless=new")  # Новый headless режим
            options.add_argument("--no-sandbox")  # Обязательно для Docker/VPS
            options.add_argument("--disable-dev-shm-usage")  # Преодолевает ограничения /dev/shm

            # Стабильность и производительность
            options.add_argument("--disable-gpu")
            options.add_argument("--disable-extensions")
            options.add_argument("--disable-plugins")
            options.add_argument("--disable-images")  # Не загружаем изображения
            options.add_argument("--disable-javascript")  # Отключаем JS если не нужен
            options.add_argument("--disable-css")  # Не загружаем CSS

            # Память и стабильность
            options.add_argument("--max_old_space_size=4096")
            options.add_argument("--disable-background-timer-throttling")
            options.add_argument("--disable-renderer-backgrounding")
            options.add_argument("--disable-backgrounding-occluded-windows")

            # User agent для обхода блокировок
            options.add_argument(
                "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")

            # Размер окна
            options.add_argument("--window-size=1920,1080")

            # Отключение логов
            options.add_argument("--log-level=3")
            options.add_argument("--silent")
            options.add_experimental_option('excludeSwitches', ['enable-logging'])
            options.add_experimental_option('useAutomationExtension', False)

            # Преференции
            prefs = {
                "profile.default_content_setting_values.notifications": 2,
                "profile.default_content_settings.popups": 0,
                "profile.managed_default_content_settings.images": 2,
                "profile.default_content_setting_values.media_stream": 2,
            }
            options.add_experimental_option("prefs", prefs)

            # Путь к Chrome
            options.binary_location = chrome_path

            # ИСПОЛЬЗУЕМ ТОЛЬКО СИСТЕМНЫЙ CHROMEDRIVER
            system_chromedriver = "/usr/local/bin/chromedriver"

            if not os.path.exists(system_chromedriver):
                raise Exception(f"Системный ChromeDriver не найден: {system_chromedriver}")

            if not os.access(system_chromedriver, os.X_OK):
                raise Exception(f"ChromeDriver не исполняемый: {system_chromedriver}")

            # Создаем сервис с системным ChromeDriver
            service = Service(system_chromedriver)

            # Создаем драйвер
            driver = webdriver.Chrome(service=service, options=options)

            # Настройки таймаутов
            driver.set_page_load_timeout(60)
            driver.implicitly_wait(10)

            # Сохраняем PID для мониторинга
            self.driver_pid = driver.service.process.pid if hasattr(driver.service, 'process') else None

            log.info(
                f"WebDriver инициализирован с системным ChromeDriver: {system_chromedriver} (PID: {self.driver_pid})")
            return driver

        except Exception as e:
            log.error(f"Ошибка инициализации WebDriver: {e}")
            raise

    def _health_check(self) -> bool:
        """Проверка состояния WebDriver"""
        try:
            if not self.driver:
                return False

            # Простая проверка
            _ = self.driver.current_url
            return True
        except Exception as e:
            log.warning(f"WebDriver не отвечает: {e}")
            return False

    def _restart_driver(self):
        """Перезапуск WebDriver при сбоях"""
        try:
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
                self.driver = None

            # Принудительное завершение процессов Chrome
            self._kill_chrome_processes()

            time.sleep(5)  # Ждем завершения процессов

            self.driver = self._init_driver()
            log.info("WebDriver успешно перезапущен")

        except Exception as e:
            log.error(f"Ошибка перезапуска WebDriver: {e}")
            raise

    def _kill_chrome_processes(self):
        """Принудительное завершение процессов Chrome"""
        try:
            import psutil
            for proc in psutil.process_iter(['pid', 'name']):
                if proc.info['name'] in ['chrome', 'chromium', 'chromium-browser']:
                    try:
                        proc.terminate()
                        proc.wait(timeout=3)
                    except (psutil.NoSuchProcess, psutil.TimeoutExpired):
                        try:
                            proc.kill()
                        except psutil.NoSuchProcess:
                            pass
        except Exception as e:
            log.warning(f"Ошибка завершения Chrome процессов: {e}")

    def _check_timeout(self):
        """Проверяет, не превышен ли общий таймаут парсинга"""
        if self.start_time and time.time() - self.start_time > PARSING_TIMEOUT:
            raise TimeoutError(f"Превышен максимальный таймаут парсинга ({PARSING_TIMEOUT} сек)")

    def _total_pages(self) -> int:
        """Получает общее количество страниц"""
        try:
            self._check_timeout()
            pager = WebDriverWait(self.driver, self.timeout).until(
                EC.presence_of_element_located((By.ID, "top_pager"))
            )
            btns = pager.find_elements(By.XPATH, ".//li[@class='button']")
            pages = int(btns[-1].get_attribute("p")) if btns else 1
            log.info(f"Найдено страниц: {pages}")
            return pages
        except Exception as e:
            log.warning(f"Не удалось определить количество страниц: {e}")
            return 1

    def _goto(self, page: int, use_input_field: bool = False):
        """Переход на указанную страницу"""
        self._check_timeout()

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                if use_input_field:
                    # Навигация через поле ввода
                    select_page_btn = WebDriverWait(self.driver, self.timeout).until(
                        EC.element_to_be_clickable((By.XPATH, "//div[@id='n_pager']//div[@class='filter-button']"))
                    )
                    self.driver.execute_script("arguments[0].click();", select_page_btn)

                    page_input = WebDriverWait(self.driver, self.timeout).until(
                        EC.presence_of_element_located((By.ID, "n_pager_pno"))
                    )
                    page_input.clear()
                    page_input.send_keys(str(page))

                    goto_btn = WebDriverWait(self.driver, self.timeout).until(
                        EC.element_to_be_clickable((By.ID, "n_pager_goto"))
                    )
                    self.driver.execute_script("arguments[0].click();", goto_btn)
                else:
                    # Обычная навигация
                    btn = WebDriverWait(self.driver, self.timeout).until(
                        EC.element_to_be_clickable((By.XPATH, f"//div[@id='top_pager']//li[@p='{page}']"))
                    )
                    self.driver.execute_script("arguments[0].click();", btn)

                time.sleep(3)
                return True

            except Exception as e:
                if attempt == max_attempts - 1:
                    log.warning(f"Навигация на страницу {page} не удалась: {e}")
                    return False

                log.warning(f"Попытка {attempt + 1} навигации не удалась, перезапуск...")
                self._restart_driver()
                self.driver.get(self.current_url)  # Возвращаемся на исходную страницу
                time.sleep(5)

    def _ids_on_page(self) -> Set[str]:
        """Извлечение ID задач с текущей страницы"""
        ids: Set[str] = set()
        max_attempts = 3

        for attempt in range(max_attempts):
            try:
                self._check_timeout()

                # Проверяем здоровье драйвера
                if not self._health_check():
                    raise Exception("WebDriver не отвечает")

                # Ждем появления iframe
                iframe = WebDriverWait(self.driver, self.timeout).until(
                    EC.presence_of_element_located((By.TAG_NAME, "iframe"))
                )

                self.driver.switch_to.frame(iframe)

                # Ждем загрузки задач
                WebDriverWait(self.driver, self.timeout).until(
                    EC.presence_of_element_located((By.XPATH, "//div[starts-with(@id,'q')]"))
                )

                tasks = self.driver.find_elements(By.XPATH, "//div[starts-with(@id,'q')]")

                for task in tasks:
                    try:
                        task_id = task.get_attribute("id")
                        if task_id and task_id.startswith('q'):
                            task_id = task_id[1:]
                            if task_id:
                                ids.add(task_id)
                    except Exception as e:
                        log.warning(f"Ошибка получения ID задачи: {e}")
                        continue

                self.driver.switch_to.default_content()
                break

            except Exception as e:
                log.warning(f"Ошибка чтения задач на странице (попытка {attempt + 1}): {e}")

                try:
                    self.driver.switch_to.default_content()
                except:
                    pass

                if attempt == max_attempts - 1:
                    log.error("Исчерпаны попытки чтения страницы")
                    break

                # Перезапуск при критических ошибках
                self._restart_driver()
                self.driver.get(self.current_url)
                time.sleep(5)

        log.info(f"Собрано ID на странице: {len(ids)}")
        return ids

    def extract_ids_sync(self, url: str) -> Set[str]:
        """Основной метод извлечения ID с улучшенной обработкой ошибок"""
        self.start_time = time.time()
        self.current_url = url

        try:
            self.driver = self._init_driver()
            log.info(f"Начало серверного парсинга ID для {url}")

            self.driver.get(url)
            time.sleep(5)

            # Сброс фильтров
            try:
                btn = WebDriverWait(self.driver, self.timeout).until(
                    EC.element_to_be_clickable((By.CLASS_NAME, "button-clear"))
                )
                self.driver.execute_script("arguments[0].click();", btn)
                time.sleep(3)
                log.info("Фильтры сброшены")
            except Exception as e:
                log.warning(f"Не удалось сбросить фильтры: {e}")

            total = self._total_pages()
            log.info(f"Будет обработано страниц: {total}")

            all_ids: Set[str] = set()
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

                        log.info(f"Обработка страницы {p}/{total}")
                        ids = self._ids_on_page()

                        if ids or p == total:
                            all_ids.update(ids)
                            page_success = True
                            log.info(f"Страница {p} обработана: {len(ids)} ID")
                        else:
                            raise Exception(f"Пустая страница {p}")

                    except Exception as e:
                        retry_count += 1
                        log.warning(f"Ошибка на странице {p}, попытка {retry_count}: {e}")

                        if retry_count < max_retries:
                            time.sleep(INITIAL_RETRY_DELAY * retry_count)
                        else:
                            failed_pages.append(p)
                            log.error(f"Страница {p} пропущена после {max_retries} попыток")

            if failed_pages:
                log.warning(f"Пропущены страницы: {failed_pages}")

            # Сохраняем результат
            if os.environ.get('PARSING_PROCESS'):
                timestamp = datetime.now().isoformat()
                if url not in store["historical_ids"]:
                    store["historical_ids"][url] = []
                store["historical_ids"][url].append({
                    "timestamp": timestamp,
                    "ids": list(all_ids)
                })
                save_store(store)

            log.info(f"Серверный парсинг завершен для {url}: {len(all_ids)} ID")
            return all_ids

        except TimeoutError as e:
            log.error(f"Тайм-аут серверного парсинга {url}: {e}")
            return set()
        except Exception as e:
            log.error(f"Ошибка серверного парсинга {url}: {e}", exc_info=True)
            return set()
        finally:
            if self.driver:
                try:
                    log.info("Закрытие серверного WebDriver")
                    self.driver.quit()
                except Exception as e:
                    log.warning(f"Ошибка при закрытии WebDriver: {e}")
                finally:
                    self.driver = None

            # Принудительная очистка
            self._kill_chrome_processes()


# Заменяем класс
TaskIdExtractor = ServerTaskIdExtractor
