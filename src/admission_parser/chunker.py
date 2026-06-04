from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .utils import INTERMEDIATE_DIR

TITLE_RE = re.compile(
    r"^(?:[【\[][^】\]]+[】\]]|[0-9０-９]+[\.．、]\s*.+|[（(][0-9０-９一二三四五六七八九十]+[）)]\s*.+)$",
    re.MULTILINE,
)
PAGE_RE = re.compile(r"^## Page (\d+)", re.MULTILINE)


@dataclass
class TextChunk:
    pdf_name: str
    page_numbers: list[int]
    title: str
    text: str


def _page_numbers(text: str) -> list[int]:
    return [int(match.group(1)) for match in PAGE_RE.finditer(text)]


def _split_without_cutting_tables(text: str, max_chars: int) -> list[str]:
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for paragraph in paragraphs:
        paragraph_size = len(paragraph) + 2
        is_table = paragraph.lstrip().startswith("|") or "\n| ---" in paragraph
        if current and size + paragraph_size > max_chars and not is_table:
            chunks.append("\n\n".join(current).strip())
            current = []
            size = 0
        current.append(paragraph)
        size += paragraph_size
    if current:
        chunks.append("\n\n".join(current).strip())
    return [chunk for chunk in chunks if chunk]


def chunk_markdown(markdown: str, pdf_name: str, max_chars: int = 6000) -> list[TextChunk]:
    matches = list(TITLE_RE.finditer(markdown))
    sections: list[tuple[str, str]] = []
    if matches:
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
            sections.append((match.group(0).strip(), markdown[start:end].strip()))
    else:
        sections = [("", markdown)]

    chunks: list[TextChunk] = []
    for title, section in sections:
        for part in _split_without_cutting_tables(section, max_chars):
            chunks.append(
                TextChunk(
                    pdf_name=pdf_name,
                    page_numbers=_page_numbers(part),
                    title=title,
                    text=part,
                )
            )
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("markdown")
    parser.add_argument("--pdf-name", required=True)
    parser.add_argument("--output", default=str(INTERMEDIATE_DIR / "chunks.json"))
    parser.add_argument("--max-chars", type=int, default=6000)
    args = parser.parse_args()
    markdown = Path(args.markdown).read_text(encoding="utf-8")
    chunks = chunk_markdown(markdown, args.pdf_name, args.max_chars)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        json.dumps([asdict(chunk) for chunk in chunks], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(args.output)


if __name__ == "__main__":
    main()
