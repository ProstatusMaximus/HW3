"""Проверки парсера: реальные requests.Response и HTML, без внешней сети."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import requests

import scraper

BOOK_URL = "https://books.toscrape.com/catalogue/book-1/index.html"
SECOND_BOOK_URL = "https://books.toscrape.com/catalogue/book-2/index.html"
SECOND_PAGE_URL = "https://books.toscrape.com/catalogue/page-2.html"


@pytest.fixture
def book_html():
    """Вернуть искусственную карточку с заранее известными значениями."""
    path = Path(__file__).parent / "fixtures" / "book.html"
    return path.read_text(encoding="utf-8")


@pytest.fixture
def mock_http(monkeypatch):
    """Подменить HTTP-транспорт; незаданный URL вызывает ошибку теста."""
    pages, calls = {}, []

    def get(session, url, **kwargs):
        assert kwargs["timeout"] == (10, 30)
        calls.append(url)
        result = pages[url]
        if isinstance(result, Exception):
            raise result
        response = requests.Response()
        response.status_code, html = result
        response.url = url
        response._content = html.encode("utf-8")
        return response

    monkeypatch.setattr(requests.Session, "get", get)
    return pages, calls


def catalogue(*links, next_page=None):
    """Сформировать минимальный каталог по переданным относительным ссылкам."""
    html = "".join(
        '<article class="product_pod"><h3>'
        f'<a href="{link}">Book</a></h3></article>'
        for link in links
    )
    if next_page:
        html += f'<li class="next"><a href="{next_page}">next</a></li>'
    return html


def test_get_book_data_values_and_types(mock_http, book_html):
    pages, calls = mock_http
    pages[BOOK_URL] = 200, book_html
    result = scraper.get_book_data(BOOK_URL)
    assert isinstance(result, dict)
    assert result == {
        "title": "Тестовая книга: Python & HTML",
        "price": 51.77,
        "currency": "GBP",
        "rating": 3,
        "availability": 22,
        "description": "Описание с HTML и кириллицей.",
        "product_information": {
            "UPC": "test-upc-001",
            "Product Type": "Books",
            "Price (excl. tax)": "£51.77",
            "Price (incl. tax)": "£51.77",
            "Tax": "£0.00",
            "Availability": "In stock (22 available)",
            "Number of reviews": "0",
        },
        "url": BOOK_URL,
    }
    assert isinstance(result["price"], float)
    assert isinstance(result["rating"], int)
    assert isinstance(result["availability"], int)
    assert calls == [BOOK_URL]


@pytest.mark.parametrize(
    "name, expected",
    [("One", 1), ("Two", 2), ("Three", 3), ("Four", 4), ("Five", 5)],
)
def test_rating_classes(mock_http, book_html, name, expected):
    pages, _ = mock_http
    pages[BOOK_URL] = 200, book_html.replace("Three extra-class", name)
    assert scraper.get_book_data(BOOK_URL)["rating"] == expected


def test_missing_description_and_out_of_stock(mock_http, book_html):
    pages, _ = mock_http
    html = book_html.replace('id="product_description"', 'id="other"')
    html = html.replace("In stock (22 available)", "Out of stock")
    pages[BOOK_URL] = 200, html
    result = scraper.get_book_data(BOOK_URL)
    assert result["description"] == ""
    assert result["availability"] == 0


@pytest.mark.parametrize(
    "old, new",
    [
        ("product_main", "missing"),
        ("Three extra-class", "Unknown"),
        ("£51.77", "invalid price"),
        ("22 available", "unknown amount"),
    ],
)
def test_invalid_card_raises(mock_http, book_html, old, new):
    pages, _ = mock_http
    pages[BOOK_URL] = 200, book_html.replace(old, new)
    with pytest.raises(ValueError):
        scraper.get_book_data(BOOK_URL)


def test_http_error_is_not_parsed(mock_http):
    pages, _ = mock_http
    pages[BOOK_URL] = 404, "Not Found"
    with pytest.raises(requests.HTTPError):
        scraper.get_book_data(BOOK_URL)


def test_pagination_and_relative_urls(
    mock_http, book_html, tmp_path, monkeypatch
):
    pages, calls = mock_http
    monkeypatch.chdir(tmp_path)
    pages[scraper.BASE_URL] = 200, catalogue(
        "book-1/index.html", next_page="page-2.html"
    )
    pages[SECOND_PAGE_URL] = 200, catalogue(
        "book-1/index.html", "book-2/index.html"
    )
    pages[BOOK_URL] = 200, book_html
    pages[SECOND_BOOK_URL] = (
        200, book_html.replace("test-upc-001", "test-upc-002")
    )
    result = scraper.scrape_books(is_save=False, delay=0)
    assert [book["url"] for book in result] == [BOOK_URL, SECOND_BOOK_URL]
    assert calls == [
        scraper.BASE_URL, BOOK_URL, SECOND_PAGE_URL, SECOND_BOOK_URL
    ]
    assert not (tmp_path / "books_data.txt").exists()


def test_save_default_filename(mock_http, book_html, tmp_path, monkeypatch):
    pages, _ = mock_http
    monkeypatch.chdir(tmp_path)
    pages[scraper.BASE_URL] = 200, catalogue("book-1/index.html")
    pages[BOOK_URL] = 200, book_html
    result = scraper.scrape_books(is_save=True, delay=0)
    text = (tmp_path / "books_data.txt").read_text(encoding="utf-8")
    assert json.loads(text) == result
    assert "Тестовая книга" in text


def test_max_pages_stops_before_next(mock_http, book_html):
    pages, calls = mock_http
    pages[scraper.BASE_URL] = 200, catalogue(
        "book-1/index.html", next_page="page-2.html"
    )
    pages[BOOK_URL] = 200, book_html
    assert len(scraper.scrape_books(max_pages=1, delay=0)) == 1
    assert SECOND_PAGE_URL not in calls


def test_cycle_raises(mock_http, book_html):
    pages, _ = mock_http
    pages[scraper.BASE_URL] = 200, catalogue(
        "book-1/index.html", next_page="page-1.html"
    )
    pages[BOOK_URL] = 200, book_html
    with pytest.raises(ValueError, match="Зацикленная"):
        scraper.scrape_books(delay=0)


def test_failed_scrape_preserves_previous_file(mock_http, tmp_path):
    pages, _ = mock_http
    pages[scraper.BASE_URL] = 200, catalogue("book-1/index.html")
    pages[BOOK_URL] = requests.Timeout("test timeout")
    output = tmp_path / "books_data.txt"
    output.write_text("previous export", encoding="utf-8")
    with pytest.raises(requests.Timeout):
        scraper.scrape_books(True, output, delay=0)
    assert output.read_text(encoding="utf-8") == "previous export"


def test_empty_catalogue_raises(mock_http):
    pages, _ = mock_http
    pages[scraper.BASE_URL] = 200, "<html><body>No books</body></html>"
    with pytest.raises(ValueError, match="не найдены книги"):
        scraper.scrape_books(delay=0)


@pytest.mark.parametrize("options", [{"max_pages": 0}, {"delay": -1}])
def test_invalid_arguments(options):
    with pytest.raises(ValueError):
        scraper.scrape_books(**options)


def test_daily_schedule_and_save_arguments(monkeypatch, tmp_path):
    calls = []

    def fake_scrape(**kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(scraper, "scrape_books", fake_scrape)
    output = tmp_path / "daily.txt"
    scheduler = scraper.create_scheduler(output_path=output)
    job, = scheduler.jobs
    assert job.unit == "days"
    assert job.interval == 1
    assert (job.at_time.hour, job.at_time.minute) == (19, 0)
    job.next_run = datetime.now() - timedelta(seconds=1)
    scheduler.run_pending()
    assert calls == [{"is_save": True, "output_path": output}]
    assert job.next_run > datetime.now()


def test_scheduler_survives_failed_download(monkeypatch, caplog):
    def failed_scrape(**kwargs):
        raise requests.Timeout("temporary failure")

    monkeypatch.setattr(scraper, "scrape_books", failed_scrape)
    scheduler = scraper.create_scheduler()
    scheduler.jobs[0].next_run = datetime.now() - timedelta(seconds=1)
    scheduler.run_pending()
    assert "Выгрузка не удалась" in caplog.text
    assert scheduler.jobs[0].next_run > datetime.now()
