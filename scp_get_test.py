#!/usr/bin/env python3
"""
scp_to_markdown.py

Получает "raw_source" (исходный код Wikidot) для страницы SCP-вики
и конвертирует его в читаемый Markdown.

Логика получения page_id и raw_source взята из оригинального проекта
scp_crawler (scp_crawler/spiders/scp.py::get_page_id и
scp_crawler/postprocessing.py::get_wiki_source).

Использование:
    python3 scp_to_markdown.py https://scp-wiki.wikidot.com/scp-173
    python3 scp_to_markdown.py scp-173 --domain scp-wiki.wikidot.com -o scp-173.md
"""

import argparse
import html
import re
import sys
import time

import httpx

DEFAULT_DOMAIN = "scp-wiki.wikidot.com"


# ---------------------------------------------------------------------------
# Шаг 1: получить page_id страницы (как в WikiMixin.get_page_id)
# ---------------------------------------------------------------------------
def get_page_id(html_text: str) -> str:
    match = re.search(r"WIKIREQUEST\.info\.pageId\s+=\s+(\d+);", html_text)
    if not match:
        raise ValueError("Не удалось найти page_id на странице (WIKIREQUEST.info.pageId)")
    return match[1]


def fetch_page_html(url: str, client: httpx.Client) -> str:
    response = client.get(url, follow_redirects=True)
    response.raise_for_status()
    return response.text


# ---------------------------------------------------------------------------
# Шаг 2: получить raw_source через ajax-module-connector (как в
# postprocessing.py::get_wiki_source)
# ---------------------------------------------------------------------------
def get_wiki_source(page_id: str, domain: str, client: httpx.Client, attempts: int = 5) -> str:
    from bs4 import BeautifulSoup

    # Реальный токен Wikidot устанавливает в куке при загрузке страницы.
    # Нужно взять его оттуда, а не передавать хардкоженную строку.
    token = client.cookies.get("wikidot_token7", domain=domain)
    if not token:
        # Резервный вариант — любое значение, которое совпадает в куке и POST-теле
        token = "123456"
        client.cookies.set("wikidot_token7", token, domain=domain)

    try:
        response = client.post(
            f"https://{domain}/ajax-module-connector.php",
            data={
                "wikidot_token7": token,
                "page_id": str(page_id),
                "moduleName": "viewsource/ViewSourceModule",
            },
        )
        response.raise_for_status()
    except httpx.HTTPError:
        attempts -= 1
        if attempts > 0:
            print(f"Не удалось загрузить source, осталось попыток: {attempts}", file=sys.stderr)
            time.sleep(1)
            return get_wiki_source(page_id, domain, client, attempts=attempts)
        raise

    page_response = response.json()
    if page_response.get("status") != "ok":
        raise ValueError(f"Wikidot вернул ошибку: {page_response}")

    soup = BeautifulSoup(page_response["body"], "lxml")
    source_div = soup.find("div", {"class": "page-source"})
    if source_div is None:
        raise ValueError("В ответе отсутствует div.page-source — возможно, страница не существует")

    raw_source = "".join(str(x) for x in source_div.contents)
    # <br/> -> перевод строки, плюс снимаем HTML-escaping (&amp; -> & и т.д.)
    return re.sub(r"<br\s*/?>", "\n", html.unescape(raw_source), flags=re.IGNORECASE)


# ---------------------------------------------------------------------------
# Шаг 3: конвертация синтаксиса Wikidot -> Markdown
# ---------------------------------------------------------------------------
def wikidot_to_markdown(source: str) -> str:
    text = source

    # --- Блоки-контейнеры Wikidot, не имеющие смысла в Markdown — убираем
    # обёртки, но оставляем содержимое.
    container_tags = [
        "div", "size", "span", "module", "iframe",
    ]
    for tag in container_tags:
        text = re.sub(rf"\[\[{tag}[^\]]*\]\]", "", text, flags=re.IGNORECASE)
        text = re.sub(rf"\[\[/{tag}\]\]", "", text, flags=re.IGNORECASE)

    # --- Коллапсируемые блоки [[collapsible show="+" hide="-"]] ... [[/collapsible]]
    def _collapsible(m):
        return f"\n<details>\n<summary>{m.group(1) or 'Показать/скрыть блок'}</summary>\n\n{m.group(2).strip()}\n\n</details>\n"

    text = re.sub(
        r'\[\[collapsible[^\]]*show="([^"]*)"[^\]]*\]\](.*?)\[\[/collapsible\]\]',
        _collapsible,
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(
        r"\[\[collapsible[^\]]*\]\](.*?)\[\[/collapsible\]\]",
        lambda m: f"\n<details>\n<summary>Показать/скрыть блок</summary>\n\n{m.group(1).strip()}\n\n</details>\n",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # --- Заголовки: ++ Заголовок, +++ Заголовок и т.д. -> #, ##, ###
    def _heading(m):
        level = len(m.group(1))
        return f"{'#' * min(level, 6)} {m.group(2).strip()}"

    text = re.sub(r"^(\++)\s*(.+)$", _heading, text, flags=re.MULTILINE)

    # --- Горизонтальная линия
    text = re.sub(r"^----+$", "\n---\n", text, flags=re.MULTILINE)

    # --- Жирный/курсив/подчёркнутый/зачёркнутый текст
    text = re.sub(r"\*\*(.+?)\*\*", r"**\1**", text)          # **bold** (уже markdown)
    text = re.sub(r"//(.+?)//", r"*\1*", text)                 # //italic// -> *italic*
    text = re.sub(r"__(.+?)__", r"**\1**", text)                # __underline__ -> bold (нет underline в md)
    text = re.sub(r"--(.+?)--", r"~~\1~~", text)                # --strike-- -> ~~strike~~

    # --- Цитаты [[quote]] ... [[/quote]] -> >
    def _quote(m):
        lines = m.group(1).strip().splitlines()
        return "\n".join(f"> {line}" for line in lines)

    text = re.sub(r"\[\[quote\]\](.*?)\[\[/quote\]\]", _quote, text, flags=re.IGNORECASE | re.DOTALL)

    # --- Изображения [[image url params]] -> ![](url)
    def _image(m):
        params = m.group(1).strip()
        url_match = re.match(r"(\S+)", params)
        url = url_match[1] if url_match else ""
        return f"![]({url})"

    text = re.sub(r"\[\[image\s+([^\]]*)\]\]", _image, text, flags=re.IGNORECASE)

    # --- Ссылки [[[target|label]]] и [[[target]]] -> [label](target)
    text = re.sub(r"\[\[\[([^\|\]]+)\|([^\]]+)\]\]\]", r"[\2](\1)", text)
    text = re.sub(r"\[\[\[([^\]]+)\]\]\]", r"[\1](\1)", text)

    # --- Обычные ссылки [http://url label] -> [label](url)
    text = re.sub(r"\[(https?://\S+)\s+([^\]]+)\]", r"[\2](\1)", text)
    text = re.sub(r"\[(https?://\S+)\]", r"<\1>", text)

    # --- Таблицы Wikidot: || ячейка || ячейка || -> markdown-таблица
    def _table_block(m):
        block = m.group(0)
        rows = [r for r in block.strip().splitlines() if r.strip().startswith("||")]
        md_rows = []
        for i, row in enumerate(rows):
            cells = [c.strip() for c in row.strip().strip("||").split("||")]
            cells = [re.sub(r"^~", "", c).strip() for c in cells]  # ~ помечает заголовок ячейки
            md_rows.append("| " + " | ".join(cells) + " |")
            if i == 0:
                md_rows.append("| " + " | ".join("---" for _ in cells) + " |")
        return "\n".join(md_rows) + "\n"

    text = re.sub(r"(?:^\|\|.*\|\|\s*$\n?)+", lambda m: "\n" + _table_block(m), text, flags=re.MULTILINE)

    # --- Списки: пустая разметка Wikidot близка к Markdown (* item, # item)
    # Wikidot использует те же символы — оставляем как есть, только нормализуем
    # отступы из табов в пробелы.
    text = re.sub(r"^\t+", lambda m: "  " * len(m.group(0)), text, flags=re.MULTILINE)

    # --- Убираем оставшиеся служебные конструкции [[...]] которые не распознали
    text = re.sub(r"\[\[(?!\[)[^\]]*\]\]", "", text)
    text = re.sub(r"\[\[/[^\]]*\]\]", "", text)

    # --- Схлопываем более двух пустых строк подряд
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip() + "\n"


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------
def normalize_url(target: str, domain: str) -> str:
    if target.startswith("http://") or target.startswith("https://"):
        return target
    slug = target.strip("/")
    return f"https://{domain}/{slug}"


def main():
    parser = argparse.ArgumentParser(description="Получить raw_source SCP-страницы и сконвертировать в Markdown")
    parser.add_argument("target", help="URL страницы (https://scp-wiki.wikidot.com/scp-173) или просто slug (scp-173)")
    parser.add_argument("--domain", default=DEFAULT_DOMAIN, help=f"Домен wikidot (по умолчанию {DEFAULT_DOMAIN})")
    parser.add_argument("-o", "--output", help="Файл для сохранения Markdown (по умолчанию печать в stdout)")
    parser.add_argument("--raw", action="store_true", help="Также вывести исходный raw_source без конвертации")
    args = parser.parse_args()

    url = normalize_url(args.target, args.domain)

    headers = {"User-Agent": "Mozilla/5.0 (compatible; scp-to-markdown/1.0)"}
    with httpx.Client(headers=headers, timeout=15) as client:
        print(f"Загружаю страницу: {url}", file=sys.stderr)
        page_html = fetch_page_html(url, client)

        page_id = get_page_id(page_html)
        print(f"page_id = {page_id}", file=sys.stderr)

        print("Запрашиваю raw_source через ajax-module-connector...", file=sys.stderr)
        raw_source = get_wiki_source(page_id, args.domain, client)

    if args.raw:
        print("----- RAW SOURCE -----", file=sys.stderr)
        print(raw_source, file=sys.stderr)
        print("-----------------------", file=sys.stderr)

    markdown = wikidot_to_markdown(raw_source)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(markdown)
        print(f"Сохранено в {args.output}", file=sys.stderr)
    else:
        print(markdown)


if __name__ == "__main__":
    main()
