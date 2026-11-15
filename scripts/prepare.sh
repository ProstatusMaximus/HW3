#!/usr/bin/env bash
# Запуск из терминала с доступом к PyPI и Books to Scrape.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-notebook.txt
# Freeze выполняется именно в изолированном окружении проекта.
.venv/bin/python -m pip freeze > requirements.txt.tmp
mv requirements.txt.tmp requirements.txt
.venv/bin/python -m ipykernel install --prefix .venv --name hw03 \
    --display-name "Python (HW03)"
.venv/bin/python -u scripts/execute_notebook.py
