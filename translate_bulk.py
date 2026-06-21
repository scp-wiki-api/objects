#!/usr/bin/env python3
"""
translate_bulk.py

Переводит Markdown-файлы из output/ с английского на русский
с помощью argostranslate и сохраняет в output-ru/.

Использование:
    python3 translate_bulk.py                        # всё из output/ → output-ru/
    python3 translate_bulk.py --input output/series-1
    python3 translate_bulk.py --no-resume            # перевести заново
"""

import argparse
import re
import sys
from pathlib import Path


def setup_argos() -> None:
    import argostranslate.package
    import argostranslate.translate

    installed = argostranslate.translate.get_installed_languages()
    from_lang = next((l for l in installed if l.code == "en"), None)
    if from_lang:
        to_lang = next((l for l in from_lang.translations_to if l.code == "ru"), None)
        if to_lang:
            return  # пакет уже установлен

    print("Скачиваю языковой пакет en→ru...", file=sys.stderr)
    argostranslate.package.update_package_index()
    available = argostranslate.package.get_available_packages()
    pkg = next(
        (p for p in available if p.from_code == "en" and p.to_code == "ru"), None
    )
    if pkg is None:
        raise RuntimeError("Пакет en→ru не найден в индексе argostranslate")
    argostranslate.package.install_from_path(pkg.download())
    print("Пакет установлен.", file=sys.stderr)


def _translate(text: str) -> str:
    import argostranslate.translate
    return argostranslate.translate.translate(text, "en", "ru")


def protect(text: str) -> tuple[str, list[str]]:
    """Заменяет нетранслируемые части текста на плейсхолдеры."""
    blocks: list[str] = []

    def save(m: re.Match) -> str:
        i = len(blocks)
        blocks.append(m.group(0))
        return f"\x00T{i}\x00"

    text = re.sub(r"```[\s\S]*?```", save, text)          # блоки кода ```
    text = re.sub(r"`[^`\n]+`", save, text)                # инлайн-код `...`
    text = re.sub(r"\]\([^)\n]*\)", save, text)            # URL в ссылках ](url)
    text = re.sub(r"https?://[^\s)>\]]+", save, text)      # голые URL
    text = re.sub(r"<[^>\n]{1,200}>", save, text)          # HTML-теги
    return text, blocks


def restore(text: str, blocks: list[str]) -> str:
    return re.sub(r"\x00T(\d+)\x00", lambda m: blocks[int(m.group(1))], text)


def translate_markdown(content: str) -> str:
    text, blocks = protect(content)

    paragraphs = re.split(r"(\n{2,})", text)  # сохраняем разделители
    result: list[str] = []

    for chunk in paragraphs:
        # Разделители и пустые строки — без изменений
        if not chunk.strip() or re.fullmatch(r"\n+", chunk):
            result.append(chunk)
            continue

        # Строки-разделители таблиц | --- | --- | — без изменений
        if re.match(r"^\s*\|[\s\-:|]+\|\s*$", chunk):
            result.append(chunk)
            continue

        # Блоки, состоящие только из плейсхолдеров — без изменений
        if re.fullmatch(r"(\x00T\d+\x00\s*)+", chunk.strip()):
            result.append(chunk)
            continue

        result.append(_translate(chunk))

    return restore("".join(result), blocks)


def process_file(src: Path, dst: Path) -> bool:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        translated = translate_markdown(src.read_text(encoding="utf-8"))
        dst.write_text(translated, encoding="utf-8")
        return True
    except Exception as exc:
        print(f" ОШИБКА: {exc}", file=sys.stderr)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Перевод SCP Markdown на русский")
    parser.add_argument(
        "--input", type=Path, default=Path("output"),
        help="Папка с исходными Markdown (по умолчанию output/)",
    )
    parser.add_argument(
        "--output", type=Path, default=Path("output-ru"),
        help="Папка для переводов (по умолчанию output-ru/)",
    )
    parser.add_argument("--resume", action="store_true", default=True,
                        help="Пропускать уже переведённые файлы (по умолчанию)")
    parser.add_argument("--no-resume", dest="resume", action="store_false",
                        help="Перевести все файлы заново")
    args = parser.parse_args()

    setup_argos()

    files = sorted(args.input.rglob("*.md"))
    total = len(files)
    ok = skipped = failed = 0

    print(f"Найдено файлов: {total}", file=sys.stderr)

    for i, src in enumerate(files, 1):
        rel = src.relative_to(args.input)
        dst = args.output / rel

        if args.resume and dst.exists():
            skipped += 1
            continue

        print(f"  [{i}/{total}] {rel}", file=sys.stderr, end="", flush=True)
        if process_file(src, dst):
            ok += 1
            print(" ✓", file=sys.stderr)
        else:
            failed += 1

    print(
        f"\nИтог: {ok} переведено, {skipped} пропущено, {failed} ошибок",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
