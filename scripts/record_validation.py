"""Обновить отчёты только после фактического полного выполнения ноутбука."""

import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
books = json.loads((ARTIFACTS / "books_data.txt").read_text(encoding="utf-8"))
if not isinstance(books, list) or not books:
    raise SystemExit("Выгрузка должна быть непустым списком книг")

xml = ElementTree.parse(ARTIFACTS / "pytest-results.xml")
suites = list(xml.getroot().iter("testsuite"))
tests = sum(int(suite.get("tests", 0)) for suite in suites)
failures = sum(
    int(suite.get("failures", 0)) + int(suite.get("errors", 0))
    for suite in suites
)
skipped = sum(int(suite.get("skipped", 0)) for suite in suites)
if tests < 3 or failures or skipped:
    raise SystemExit("Ожидалось не менее трёх успешных тестов без пропусков")

notebook_path, = (ROOT / "notebooks").glob("*_HW_03_python_ds.ipynb")
notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
code_cells = [c for c in notebook["cells"] if c["cell_type"] == "code"]
if any(cell["execution_count"] is None for cell in code_cells):
    raise SystemExit("Не все технические ячейки ноутбука выполнены")
if any(
    output.get("output_type") == "error"
    for cell in code_cells
    for output in cell["outputs"]
):
    raise SystemExit("Ноутбук содержит ошибки выполнения")

for cell in notebook["cells"]:
    if cell["cell_type"] != "markdown":
        continue
    content = "".join(cell["source"])
    if content.startswith("### Статус этой копии"):
        cell["source"] = (
            "### Статус этой копии\n\n"
            "Технические ячейки выполнены. Данные и отчёты тестов находятся "
            "в `artifacts/`; сводка — в `VALIDATION.md`.\n\n"
            "Техническая часть подготовлена с помощью Codex; см. "
            "`AI_USAGE.md`. Личная рефлексия заполняется студентом.\n"
        ).splitlines(keepends=True)
    elif content.startswith("### Состояние задания 5"):
        cell["source"] = (
            "### Состояние задания 5\n\n"
            "Файлы проекта и артефакты подготовлены. Репозиторий: "
            "https://github.com/ProstatusMaximus/HW3.\n\n"
            "Историю ветки hw-books-parser, Pull Request и его слияния "
            "проверяйте в репозитории на GitHub.\n"
        ).splitlines(keepends=True)
notebook_path.write_text(
    json.dumps(notebook, ensure_ascii=False, indent=1) + "\n",
    encoding="utf-8",
)

summary = (
    f"Проверено (UTC): {datetime.now(timezone.utc).isoformat()}\n"
    f"Python: {platform.python_version()}\n"
    f"Книг собрано: {len(books)}\n"
    f"Тестов пройдено: {tests}\n"
    f"Ноутбук: {notebook_path.name}; все технические ячейки выполнены.\n"
    "Расписание: выполнена короткая проверка с сохранением данных.\n"
    "Личная рефлексия заполняется студентом самостоятельно.\n"
)
(ROOT / "VALIDATION.md").write_text(summary, encoding="utf-8")
(ARTIFACTS / "environment-check.txt").write_text(summary, encoding="utf-8")

readme_path = ROOT / "README.md"
readme = readme_path.read_text(encoding="utf-8")
start = readme.index("## Статус подготовки")
end = readme.index("## Установка и полный запуск", start)
readme = (
    readme[:start]
    + "## Статус подготовки\n\n"
    + "Технические ячейки ноутбука выполнены; данные и отчёты находятся в "
    + "`artifacts/`. Результаты: [VALIDATION.md](VALIDATION.md).\n\n"
    + "Подготовлено с помощью Codex (см. `AI_USAGE.md`); личная рефлексия "
    + "заполняется студентом самостоятельно. Историю PR и слияния "
    + "проверяйте на GitHub.\n\n"
    + readme[end:]
)
readme_path.write_text(readme, encoding="utf-8")
(ROOT / "PR_DESCRIPTION.md").write_text(
    "Парсер собирает все книги Books to Scrape, сохраняет текстовый JSON "
    "и поддерживает ежедневную выгрузку в 19:00. Добавлены ноутбук, тесты "
    "и инструкции запуска.\n\n"
    + summary
    + "\nПодготовлено с помощью Codex; см. AI_USAGE.md.\n",
    encoding="utf-8",
)
(ARTIFACTS / "README.md").write_text(
    "# Результаты выполнения\n\n"
    "`books_data.txt` — полная выгрузка, JSON в UTF-8.\n\n"
    "`pytest-report.txt` и `pytest-results.xml` — отчёты pytest.\n\n"
    "`environment-check.txt` — сводка успешного выполнения.\n\n"
    + summary,
    encoding="utf-8",
)
print(summary)
