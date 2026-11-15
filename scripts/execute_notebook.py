"""Выполнить ноутбук в ядре проекта и сохранить фактические выводы ячеек."""

import os
import time
from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]


class ProgressNotebookClient(NotebookClient):
    """Сохранять выводы в ноутбук и показывать потоковый вывод в терминале."""

    def process_message(self, msg, cell, cell_index):
        """Передать сообщение nbclient и вывести текст stdout или stderr."""
        output = super().process_message(msg, cell, cell_index)
        if msg["msg_type"] == "stream":
            print(msg["content"]["text"], end="", flush=True)
        return output


started_at = {}


def show_cell_start(cell, cell_index):
    """Показать номер и первую строку выполняемой ячейки."""
    if cell["cell_type"] != "code":
        return
    started_at[cell_index] = time.monotonic()
    first_line = cell["source"].splitlines()[0] if cell["source"] else ""
    print(f"\nЯчейка {cell_index + 1}: {first_line}", flush=True)


def show_cell_end(cell, cell_index, execute_reply):
    """Сообщить статус ячейки и затраченное время."""
    elapsed = time.monotonic() - started_at[cell_index]
    status = execute_reply["content"]["status"]
    print(
        f"Ячейка {cell_index + 1}: {status}, {elapsed:.1f} с",
        flush=True,
    )


def main():
    """Найти ноутбук, выполнить его с прогрессом и сохранить выводы."""
    notebooks = list((ROOT / "notebooks").glob("*_HW_03_python_ds.ipynb"))
    if len(notebooks) != 1:
        raise SystemExit("Нужен ровно один notebooks/*_HW_03_python_ds.ipynb")

    path = notebooks[0]
    notebook = nbformat.read(path, as_version=4)
    client = ProgressNotebookClient(
        notebook,
        timeout=7200,
        kernel_name="hw03",
        resources={"metadata": {"path": str(ROOT)}},
        on_cell_start=show_cell_start,
        on_cell_executed=show_cell_end,
    )
    # Регистрация в .venv не меняет глобальную конфигурацию Jupyter.
    kernel_path = str(ROOT / ".venv" / "share" / "jupyter")
    previous_path = os.environ.get("JUPYTER_PATH")
    os.environ["JUPYTER_PATH"] = (
        os.pathsep.join([kernel_path, previous_path])
        if previous_path else kernel_path
    )
    try:
        print(f"Выполняется: {path.name}", flush=True)
        print(
            "Полный сбор загружает каталог и каждую книгу отдельно; "
            "он может занять десятки минут. Прогресс показан ниже.",
            flush=True,
        )
        client.execute()
    finally:
        # Сохраняются реальные выводы, включая возникшую ошибку.
        nbformat.write(notebook, path)
        print(f"Состояние ноутбука сохранено: {path.name}", flush=True)
    print(f"Выполнен и сохранён: {path.name}", flush=True)


if __name__ == "__main__":
    main()
