# SCP Markdown Archiver

Инструмент для скачивания статей с [SCP Wiki](https://scp-wiki.wikidot.com/) и конвертации их в Markdown.

## Структура

```
scp_get_test.py   — скачать одну статью
scp_bulk.py       — скачать серии 1–10 целиком
output/           — результат (серии → Markdown-файлы)
errors.log        — статьи, которые не удалось скачать
```

## Установка

```bash
pip install -r requirements.txt
```

## Использование

### Одна статья

```bash
python3 scp_get_test.py scp-173
python3 scp_get_test.py scp-173 -o scp-173.md
python3 scp_get_test.py https://scp-wiki.wikidot.com/scp-173 --raw
```

### Все серии (1–10)

```bash
python3 scp_bulk.py                    # все серии, задержка 200 мс
python3 scp_bulk.py --series 1 2 3    # только серии 1, 2, 3
python3 scp_bulk.py --delay 0.5       # задержка 500 мс
python3 scp_bulk.py --no-resume       # перескачать всё заново
```

Файлы сохраняются в `output/series-N/scp-XXX.md`.  
Уже скачанные файлы пропускаются по умолчанию (`--resume`).

## Автоматическое обновление

GitHub Actions workflow (`.github/workflows/daily-update.yml`) запускается каждый день в 00:00 UTC и при ручном запуске из вкладки Actions. Новые и изменившиеся статьи коммитятся автоматически.

Для работы workflow убедитесь, что в настройках репозитория включено:  
**Settings → Actions → General → Workflow permissions → Read and write permissions**

## Лицензия

Код этого репозитория — MIT (см. файл `LICENSE`).

Весь текстовый контент в папке `output/` взят с сайта [scp-wiki.wikidot.com](https://scp-wiki.wikidot.com/) и его авторов. Он распространяется под лицензией **[Creative Commons Attribution-ShareAlike 3.0](https://creativecommons.org/licenses/by-sa/3.0/)** — то же условие распространяется на производные работы.
