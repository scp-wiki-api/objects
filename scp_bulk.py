#!/usr/bin/env python3
"""
scp_bulk.py

Скачивает все статьи SCP серий 1-10 с scp-wiki.wikidot.com и
сохраняет их как Markdown-файлы в папку output/series-N/.

Использование:
    python3 scp_bulk.py                      # все серии 1-10, задержка 200 мс
    python3 scp_bulk.py --series 1 2         # только серии 1 и 2
    python3 scp_bulk.py --delay 0.5          # задержка 500 мс
    python3 scp_bulk.py --no-resume          # перескачать всё заново
"""

import argparse
import re
import sys
import time
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from scp_get_test import (
    DEFAULT_DOMAIN,
    fetch_page_html,
    get_page_id,
    get_wiki_source,
    wikidot_to_markdown,
)

OUTPUT_DIR = Path("output")
ERRORS_LOG = Path("errors.log")


def series_index_url(n: int) -> str:
    if n == 1:
        return f"https://{DEFAULT_DOMAIN}/scp-series"
    return f"https://{DEFAULT_DOMAIN}/scp-series-{n}"


def get_article_links(series_num: int, client: httpx.Client) -> list[str]:
    url = series_index_url(series_num)
    print(f"[series-{series_num}] Индекс: {url}", file=sys.stderr)
    page_html = fetch_page_html(url, client)
    soup = BeautifulSoup(page_html, "lxml")

    content = soup.find("div", id="page-content")
    if content is None:
        raise ValueError(f"Не найден #page-content на {url}")

    seen: set[str] = set()
    links: list[str] = []
    for a in content.find_all("a", href=True):
        href: str = a["href"]
        if re.match(r"^/scp-\d+$", href) and href not in seen:
            seen.add(href)
            links.append(f"https://{DEFAULT_DOMAIN}{href}")

    return links


def process_article(
    url: str,
    series_num: int,
    client: httpx.Client,
    delay: float,
) -> bool:
    slug = url.rstrip("/").split("/")[-1]
    out_path = OUTPUT_DIR / f"series-{series_num}" / f"{slug}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        page_html = fetch_page_html(url, client)
        page_id = get_page_id(page_html)
        raw_source = get_wiki_source(page_id, DEFAULT_DOMAIN, client)
        markdown = wikidot_to_markdown(raw_source)
        out_path.write_text(markdown, encoding="utf-8")
        return True
    except Exception as exc:
        with ERRORS_LOG.open("a", encoding="utf-8") as f:
            f.write(f"{url}\t{exc}\n")
        print(f" ОШИБКА: {exc}", file=sys.stderr)
        return False
    finally:
        if delay > 0:
            time.sleep(delay)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk-загрузчик SCP серий 1-10 в Markdown")
    parser.add_argument(
        "--series", type=int, nargs="+", default=list(range(1, 11)),
        metavar="N", help="Серии для загрузки (по умолчанию 1-10)",
    )
    parser.add_argument(
        "--delay", type=float, default=0.2,
        help="Задержка между запросами в секундах (по умолчанию 0.2)",
    )
    parser.add_argument(
        "--resume", action="store_true", default=True,
        help="Пропускать уже скачанные файлы (по умолчанию включено)",
    )
    parser.add_argument(
        "--no-resume", dest="resume", action="store_false",
        help="Перескачать все файлы заново",
    )
    args = parser.parse_args()

    headers = {"User-Agent": "Mozilla/5.0 (compatible; scp-bulk/1.0)"}

    with httpx.Client(headers=headers, timeout=30) as client:
        for series_num in sorted(set(args.series)):
            links = get_article_links(series_num, client)
            total = len(links)
            ok = skipped = failed = 0

            print(f"[series-{series_num}] Найдено статей: {total}", file=sys.stderr)

            for i, url in enumerate(links, 1):
                slug = url.split("/")[-1]
                out_path = OUTPUT_DIR / f"series-{series_num}" / f"{slug}.md"

                if args.resume and out_path.exists():
                    skipped += 1
                    continue

                print(f"  [{i}/{total}] {slug}", file=sys.stderr, end="", flush=True)
                success = process_article(url, series_num, client, args.delay)
                if success:
                    ok += 1
                    print(" ✓", file=sys.stderr)
                else:
                    failed += 1

            print(
                f"[series-{series_num}] Итог: {ok} скачано, {skipped} пропущено, {failed} ошибок",
                file=sys.stderr,
            )

    if ERRORS_LOG.exists() and ERRORS_LOG.stat().st_size > 0:
        print(f"\nОшибки сохранены в {ERRORS_LOG}", file=sys.stderr)


if __name__ == "__main__":
    main()
