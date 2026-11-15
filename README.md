# Books to Scrape — домашнее задание 3

Учебный проект собирает все книги с [Books to Scrape](https://books.toscrape.com/),
сохраняет данные в текстовый файл и запускает повторный сбор ежедневно в 19:00.
Для каждой книги извлекаются название, цена в GBP, рейтинг от 1 до 5,
количество в наличии, описание и вся таблица Product Information.

## Статус подготовки

Технические ячейки ноутбука выполнены; данные и отчёты находятся в `artifacts/`. Результаты: [VALIDATION.md](VALIDATION.md).

Подготовлено с помощью Codex (см. `AI_USAGE.md`); личная рефлексия заполняется студентом самостоятельно. Историю PR и слияния проверяйте на GitHub.

## Установка и полный запуск

Нужен Python 3.10 или новее и доступ к PyPI и Books to Scrape.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.in
python -m pip freeze > requirements.txt
pytest
python scraper.py --output artifacts/books_data.txt
```

`requirements.in` содержит прямые зависимости проекта. После установки
`requirements.txt` обновляется командой `pip freeze` в новой виртуальной
среде и фиксирует также транзитивные зависимости. Пока полная установка
недоступна, в `requirements.txt` оставлен исходный список зависимостей;
он ещё не является результатом `pip freeze`.

Библиотеки: `requests` — HTTP, `beautifulsoup4` — HTML,
`schedule` — расписание, `pytest` — автотесты.
Для автоматического выполнения ноутбука дополнительно используются
`nbformat`, `nbclient`, `ipykernel` из `requirements-notebook.txt`.

Одна команда устанавливает зависимости в `.venv`, фиксирует их версии,
выполняет ноутбук, собирает весь каталог и сохраняет отчёт тестов:

```bash
bash scripts/prepare.sh
```

Она завершится с ошибкой при неудачной установке, сборе данных или тестах.
Ноутбук сохраняется с фактическими выводами, включая возникшую ошибку.
Полный сбор занимает несколько минут: загружаются страницы каталога
и отдельная страница каждой книги, между запросами есть пауза.

Во время выполнения в терминале показаны номера ячеек, страницы каталога
и число собранных книг; вывод одновременно сохраняется в ноутбуке.
Сетевой сбор может занять десятки минут. Предупреждение IPKernelApp
о TCP-транспорте само по себе не означает остановку выполнения.

## Примеры использования

```bash
# Быстрая проверка на одной странице; файл содержит только эту часть каталога.
python scraper.py --max-pages 1 --output artifacts/sample_books.txt

# Весь каталог.
python scraper.py --output artifacts/books_data.txt

# Ежедневная полная выгрузка в 19:00.
python scraper.py --schedule --at 19:00 --output artifacts/books_data.txt
```

Время берётся из часового пояса компьютера; для московского времени
на компьютере должен быть выбран соответствующий часовой пояс.
Планировщик работает, пока запущен процесс и компьютер не спит.
Он не устанавливается как системная служба и не запускается после перезагрузки
самостоятельно. Остановка — `Ctrl+C`. Цикл проверяет задачи раз в секунду.
Для ручной проверки можно передать ближайшее время через `--at HH:MM`.
В ноутбуке есть короткая проверка реального срабатывания расписания
с сохранением уже собранных данных через несколько секунд.

```python
from scraper import get_book_data, scrape_books

book = get_book_data(
    "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
)
books = scrape_books(is_save=False)  # Только вернуть список.
books = scrape_books(is_save=True)   # books_data.txt в текущей папке.
```

В `books_data.txt` находится JSON-массив, несмотря на расширение `.txt`,
указанное в задании. Прочитать файл можно через `json.load`.
`price` — число, `rating` и `availability` — целые числа;
исходные значения таблицы сохраняются строками в `product_information`.
Пустое описание становится `""`; отсутствие обязательных полей вызывает ошибку.
При сбое сбора предыдущий файл не заменяется неполными данными.

## Как устроено решение

1. `get_soup` загружает страницу с тайм-аутом и проверяет HTTP-статус.
2. `get_book_data` находит HTML-элементы CSS-селекторами и преобразует значения.
3. `scrape_books` обходит карточки и ссылку `next` до последней страницы;
   `urljoin` превращает относительные ссылки в абсолютные.
4. `save_books` записывает новый файл и затем атомарно заменяет предыдущий.
5. `create_scheduler` создаёт ежедневную задачу, `run_scheduler` ждёт её запуска.

Число страниц не зашито в код. Повторяющиеся ссылки на книги исключаются,
зацикленная пагинация вызывает ошибку. Один объект Session переиспользует
соединения и повторяет временно неудачные GET-запросы.

## Тесты

```bash
pytest
python -m pytest -q tests/test_scraper.py --junitxml=artifacts/pytest-results.xml
```

Тесты работают без сети после установки зависимостей. Подменяется HTTP-запрос,
но BeautifulSoup разбирает настоящий HTML из искусственной фикстуры.
Проверяются поля и типы, все рейтинги, отсутствие описания, нулевой остаток,
ошибки HTTP и разметки, пагинация, повторные ссылки, сохранение и его отключение,
лимит страниц, сохранность старого файла при ошибке и параметры расписания.
Успех этих тестов не заменяет проверку на живом сайте.

## Структура

```text
scraper.py                  # Парсер и CLI
requirements.in             # Прямые зависимости
requirements.txt            # После установки — результат pip freeze
requirements-notebook.txt   # Дополнения для ноутбука
pytest.ini
notebooks/
  ФИО_HW_03_python_ds.ipynb
tests/
  test_scraper.py
  fixtures/book.html
artifacts/
scripts/
  prepare.sh
  execute_notebook.py
  record_validation.py
  finish.sh
```

Переименуйте `ФИО_HW_03_python_ds.ipynb`, заменив `ФИО` полными фамилией,
именем и отчеством. Исходные вопросы рефлексии сохранены без ответов.

## Git и GitHub

Целевой репозиторий: <https://github.com/ProstatusMaximus/HW3>.
Он должен быть Public; текущее значение видимости из среды подготовки
не проверено. Для пустого репозитория сначала нужен базовый коммит в `main`,
затем отдельная ветка с решением, чтобы можно было создать Pull Request.

После переноса файлов в клонированный репозиторий и успешных проверок:

```bash
# Укажите собственные ФИО и email для коммитов.
git config user.name "Ваше ФИО"
git config user.email "Ваш email"

# Только если репозиторий ещё не содержит ни одного коммита:
# В пустом клоне уже выбрана ветка main.
git commit --allow-empty -m "Initialize homework repository"
git push -u origin main

git switch -c hw-books-parser
git add scraper.py README.md requirements.in requirements*.txt pytest.ini .gitignore
git add AI_USAGE.md PR_DESCRIPTION.md
git add notebooks tests artifacts scripts
git commit -m "Add book scraper, daily schedule, notebook and tests"
git push -u origin hw-books-parser

gh pr create --base main --head hw-books-parser \
  --title "HW3: парсер книг, расписание и тесты" --body-file PR_DESCRIPTION.md
gh pr merge --merge
git switch main
git pull --ff-only origin main
```

Файл `PR_DESCRIPTION.md` содержит шаблон описания; перед созданием PR
обновите фактические результаты проверок. После выполнения шагов также
обновите раздел статуса в README и ноутбуке.

## Источники и использование ИИ

- [Books to Scrape](https://books.toscrape.com/).
- [Карточка для самопроверки](https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html).
- [Официальные примеры schedule](https://schedule.readthedocs.io/en/stable/examples.html).
- `AI_USAGE.md` фиксирует участие помощника и запросы; это техническая запись,
  а не личная рефлексия студента.
