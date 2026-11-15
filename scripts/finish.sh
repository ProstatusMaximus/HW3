#!/usr/bin/env bash
# Выполнить из обычного терминала: bash scripts/finish.sh.
# Все сетевые проверки должны пройти до отправки решения на GitHub.
set -euo pipefail
cd "$(dirname "$0")/.."

for program in python3 git gh; do
    if ! command -v "$program" >/dev/null; then
        echo "Не найдена команда: $program" >&2
        exit 1
    fi
done

case "$(git remote get-url origin)" in
    https://github.com/ProstatusMaximus/HW3.git|git@github.com:ProstatusMaximus/HW3.git)
        ;;
    *)
        echo "Ожидался репозиторий ProstatusMaximus/HW3; отправка отменена." >&2
        exit 1
        ;;
esac

gh auth status
if ! git var GIT_AUTHOR_IDENT >/dev/null 2>&1; then
    read -r -p "Имя для подписи коммитов: " author_name
    read -r -p "Email для подписи коммитов: " author_email
    test -n "$author_name" && test -n "$author_email"
    git config --local user.name "$author_name"
    git config --local user.email "$author_email"
fi

if test -f "notebooks/ФИО_HW_03_python_ds.ipynb"; then
    read -r -p "Фамилия Имя Отчество для имени ноутбука: " student_name
    if test -z "$student_name" || [[ "$student_name" == *'/'* ]]; then
        echo "Введите непустое ФИО без символа /." >&2
        exit 1
    fi
    notebook_name="${student_name// /_}_HW_03_python_ds.ipynb"
    if test -e "notebooks/$notebook_name"; then
        echo "Файл уже существует: $notebook_name" >&2
        exit 1
    fi
    mv "notebooks/ФИО_HW_03_python_ds.ipynb" "notebooks/$notebook_name"
fi

# Включает сбор всего каталога, сохранение, проверку schedule и pytest.
bash scripts/prepare.sh
.venv/bin/python scripts/record_validation.py

if ! git rev-parse --verify HEAD >/dev/null 2>&1; then
    git symbolic-ref HEAD refs/heads/main
    git commit --allow-empty -m "Initialize homework repository"
    git push -u origin main
fi

current_branch="$(git branch --show-current)"
if test "$current_branch" != "hw-books-parser"; then
    if git show-ref --verify --quiet refs/heads/hw-books-parser; then
        echo "Ветка hw-books-parser уже существует: переключитесь на неё и повторите." >&2
        exit 1
    fi
    git switch -c hw-books-parser
fi

git add scraper.py README.md AI_USAGE.md PR_DESCRIPTION.md VALIDATION.md
git add requirements.in requirements.txt requirements-notebook.txt pytest.ini
git add .gitignore notebooks tests artifacts scripts
if ! git diff --cached --quiet; then
    git commit -m "Add book scraper, daily schedule, notebook and tests"
fi

if test "$(gh repo view ProstatusMaximus/HW3 --json isPrivate --jq .isPrivate)" = true; then
    gh repo edit ProstatusMaximus/HW3 --visibility public \
        --accept-visibility-change-consequences
fi
git push -u origin hw-books-parser

pr_url="$(gh pr list --repo ProstatusMaximus/HW3 --base main \
    --head hw-books-parser --state open --json url --jq '.[0].url // empty')"
if test -z "$pr_url"; then
    pr_url="$(gh pr create --repo ProstatusMaximus/HW3 --base main \
        --head hw-books-parser --title "HW3: парсер книг, расписание и тесты" \
        --body-file PR_DESCRIPTION.md)"
fi
gh pr merge "$pr_url" --merge
git switch main
git pull --ff-only origin main
gh pr view "$pr_url" --json url,state --jq '"PR: " + .url + " (" + .state + ")"'
gh repo view ProstatusMaximus/HW3 --json url,isPrivate
echo "Для сдачи: https://github.com/ProstatusMaximus/HW3"
echo "Личную рефлексию нужно заполнить самостоятельно перед сдачей."
