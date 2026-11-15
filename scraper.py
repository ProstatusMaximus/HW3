"""Сбор каталога Books to Scrape и ежедневная выгрузка в 19:00."""

import argparse
import json
import logging
import os
import re
import tempfile
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
import schedule
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://books.toscrape.com/catalogue/page-1.html"
RATINGS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}
LOGGER = logging.getLogger(__name__)


def create_session() -> requests.Session:
    """Вернуть HTTP-сессию с тремя повторами временных сбоев GET-запросов."""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers["User-Agent"] = "BooksScraper/1.0 (homework)"
    return session


def get_soup(url: str, session: requests.Session) -> BeautifulSoup:
    """Загрузить URL через session, проверить статус и вернуть HTML-дерево."""
    response = session.get(url, timeout=(10, 30))
    response.raise_for_status()
    # Сайт использует UTF-8; декодирование исключает ошибочное «Â£».
    return BeautifulSoup(
        response.content, "html.parser", from_encoding="utf-8"
    )


def get_book_data(
    book_url: str, session: requests.Session | None = None
) -> dict:
    """Собрать полную карточку книги.

    Args:
        book_url: Абсолютный URL страницы книги.
        session: Сессия для повторного использования соединений или None.

    Returns:
        Словарь с title (str), price (float, GBP), rating (int, 1–5),
        availability (int), description (str), product_information (dict),
        currency (str) и url (str). Нет описания — возвращается пустая строка.

    Raises:
        requests.RequestException: Не удалось загрузить страницу.
        ValueError: В HTML отсутствуют обязательные данные или они некорректны.
    """
    if session is None:
        with create_session() as owned_session:
            return get_book_data(book_url, session=owned_session)

    soup = get_soup(book_url, session)
    main = soup.select_one(".product_main")
    table = soup.select_one("table.table-striped")
    if main is None or table is None:
        raise ValueError(f"Нет карточки книги или таблицы: {book_url}")

    title = main.select_one("h1")
    price = main.select_one(".price_color")
    stars = main.select_one(".star-rating")
    stock = main.select_one(".availability")
    if any(element is None for element in (title, price, stars, stock)):
        raise ValueError(f"Неполная карточка книги: {book_url}")

    price_text = price.get_text(strip=True)
    price_match = re.fullmatch(r"£(\d+\.\d{2})", price_text)
    if price_match is None:
        raise ValueError(f"Неизвестный формат цены: {price_text}")

    rating = next(
        (RATINGS[name] for name in stars.get("class", []) if name in RATINGS),
        None,
    )
    if rating is None:
        raise ValueError(f"Неизвестный рейтинг: {book_url}")

    stock_text = stock.get_text(" ", strip=True)
    stock_match = re.search(r"(\d+)\s+available", stock_text, re.IGNORECASE)
    if stock_match:
        available = int(stock_match.group(1))
    elif "out of stock" in stock_text.lower():
        available = 0
    else:
        raise ValueError(f"Неизвестный остаток: {stock_text}")

    information = {}
    for row in table.select("tr"):
        heading, value = row.find("th"), row.find("td")
        if heading is None or value is None:
            raise ValueError(f"Некорректная строка таблицы: {book_url}")
        key = heading.get_text(strip=True)
        information[key] = value.get_text(" ", strip=True)
    if not information:
        raise ValueError(f"Пустая таблица Product Information: {book_url}")

    description = soup.select_one("#product_description + p")
    return {
        "title": title.get_text(strip=True),
        "price": float(price_match.group(1)),
        "currency": "GBP",
        "rating": rating,
        "availability": available,
        "description": (
            description.get_text(" ", strip=True) if description else ""
        ),
        "product_information": information,
        "url": book_url,
    }


def save_books(books: list[dict], output_path: str | Path) -> None:
    """Атомарно сохранить список books как JSON в UTF-8 по пути output_path.

    Расширение .txt соответствует заданию; содержимое читается json.load.
    Старый файл заменяется только после успешной записи нового файла.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(books, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def scrape_books(
    is_save: bool = False,
    output_path: str | Path = "books_data.txt",
    start_url: str = BASE_URL,
    max_pages: int | None = None,
    delay: float = 0.2,
) -> list[dict]:
    """Пройти страницы каталога по ссылке next и собрать все карточки.

    Args:
        is_save: Сохранять ли результат; False не изменяет файлы.
        output_path: Путь к JSON-файлу, по умолчанию в текущей папке.
        start_url: Абсолютный адрес начальной страницы каталога.
        max_pages: Лимит страниц для быстрой проверки; None — весь каталог.
        delay: Пауза между запросами в секундах, неотрицательное число.

    Returns:
        Список словарей get_book_data без повторений URL книг.

    Raises:
        ValueError: Неверный аргумент, пустой каталог или цикл пагинации.
        requests.RequestException: Ошибка сети; прежняя выгрузка сохраняется.
    """
    if max_pages is not None and max_pages < 1:
        raise ValueError("max_pages: положительное число или None")
    if delay < 0:
        raise ValueError("delay не может быть отрицательным")

    books, visited_pages, visited_books = [], set(), set()
    page_url = start_url
    with create_session() as session:
        while page_url:
            if page_url in visited_pages:
                raise ValueError(f"Зацикленная пагинация: {page_url}")
            visited_pages.add(page_url)
            soup = get_soup(page_url, session)
            links = soup.select("article.product_pod h3 a[href]")
            if not links:
                raise ValueError(
                    f"В каталоге не найдены книги: {page_url}"
                )
            LOGGER.info(
                "Страница %d: найдено %d ссылок; %s",
                len(visited_pages), len(links), page_url,
            )
            for link_number, link in enumerate(links, start=1):
                book_url = urljoin(page_url, link["href"])
                if book_url not in visited_books:
                    time.sleep(delay)
                    books.append(get_book_data(book_url, session=session))
                    visited_books.add(book_url)
                if link_number % 5 == 0 or link_number == len(links):
                    LOGGER.info(
                        "Страница %d: обработано %d/%d; всего книг: %d",
                        len(visited_pages), link_number,
                        len(links), len(books),
                    )
            LOGGER.info(
                "Страниц: %d; книг: %d", len(visited_pages), len(books)
            )
            if max_pages is not None and len(visited_pages) >= max_pages:
                break
            next_link = soup.select_one("li.next a[href]")
            page_url = (
                urljoin(page_url, next_link["href"]) if next_link else None
            )
            if page_url:
                time.sleep(delay)
    if is_save:
        save_books(books, output_path)
    return books


def scheduled_scrape(output_path: str | Path) -> None:
    """Выгрузить каталог в output_path; записать сбой и ждать завтра."""
    try:
        books = scrape_books(is_save=True, output_path=output_path)
        LOGGER.info(
            "Выгрузка завершена: %d книг, %s", len(books), output_path
        )
    except (requests.RequestException, ValueError, OSError):
        LOGGER.exception("Выгрузка не удалась; следующий запуск по расписанию")


def create_scheduler(
    run_at: str = "19:00", output_path: str | Path = "books_data.txt"
) -> schedule.Scheduler:
    """Вернуть планировщик ежедневной выгрузки.

    Args:
        run_at: Время HH:MM (либо HH:MM:SS) в часовом поясе компьютера.
        output_path: Путь для сохранения результата ежедневного сбора.

    Returns:
        Отдельный Scheduler с одной задачей; цикл ожидания ещё не запущен.
    """
    scheduler = schedule.Scheduler()
    scheduler.every().day.at(run_at).do(scheduled_scrape, output_path)
    return scheduler


def run_scheduler(
    run_at: str = "19:00", output_path: str | Path = "books_data.txt"
) -> None:
    """Ожидать ежедневную выгрузку в run_at; остановиться по Ctrl+C."""
    scheduler = create_scheduler(run_at, output_path)
    LOGGER.info("Следующий запуск: %s", scheduler.next_run)
    try:
        while True:
            scheduler.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        LOGGER.info("Планировщик остановлен")


def main() -> None:
    """Прочитать аргументы CLI и запустить сбор либо ежедневный планировщик."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schedule", action="store_true")
    parser.add_argument("--at", default="19:00", help="Местное время HH:MM")
    parser.add_argument("--output", default="books_data.txt")
    parser.add_argument("--max-pages", type=int, default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    if args.schedule:
        if args.max_pages is not None:
            parser.error("--max-pages применяется только к однократному сбору")
        run_scheduler(args.at, args.output)
    else:
        books = scrape_books(True, args.output, max_pages=args.max_pages)
        print(f"Сохранено {len(books)} книг в {args.output}")


if __name__ == "__main__":
    main()
