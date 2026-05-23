from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import fitz
import pdfplumber

from .utils import ensure_dir, write_json

DEFAULT_KEYWORDS = ["出願期間", "提出書類", "受験票", "検定料", "入学願書"]


def _page_image_count(page: fitz.Page) -> int:
    return len(page.get_images(full=True))


def profile_pdf(
    pdf_path: str | Path,
    output_dir: str | Path,
    keywords: list[str] | None = None,
) -> dict[str, Any]:
    pdf_path = Path(pdf_path)
    output_dir = ensure_dir(output_dir)
    keywords = keywords or DEFAULT_KEYWORDS
    relevant_pages: list[int] = []
    pages: list[dict[str, Any]] = []

    doc = fitz.open(pdf_path)
    with pdfplumber.open(pdf_path) as plumber_pdf:
        for idx, page in enumerate(doc):
            page_no = idx + 1
            fitz_text = page.get_text("text") or ""
            plumber_page = plumber_pdf.pages[idx]
            plumber_text = plumber_page.extract_text() or ""
            tables = plumber_page.find_tables() or []
            hit_keywords = [keyword for keyword in keywords if keyword in fitz_text or keyword in plumber_text]
            is_scanned = len((fitz_text + plumber_text).strip()) < 20 and _page_image_count(page) > 0
            if hit_keywords:
                relevant_pages.append(page_no)

            pages.append(
                {
                    "page": page_no,
                    "hit_keywords": hit_keywords,
                    "char_count_fitz": len(fitz_text),
                    "char_count_pdfplumber": len(plumber_text),
                    "table_count": len(tables),
                    "image_count": _page_image_count(page),
                    "suspected_scanned": is_scanned,
                    "fitz_blocks": page.get_text("blocks"),
                    "fitz_words_sample": page.get_text("words")[:200],
                    "pdfplumber_text": plumber_text,
                    "pdfplumber_tables": [table.extract() for table in tables],
                }
            )

    result = {
        "pdf_name": pdf_path.name,
        "keywords": keywords,
        "relevant_pages": sorted(set(relevant_pages)),
        "pages": pages,
    }
    write_json(
        output_dir / f"{pdf_path.stem}_relevant_pages.json",
        {"pdf_name": pdf_path.name, "relevant_pages": result["relevant_pages"]},
    )
    write_json(output_dir / f"{pdf_path.stem}_profile.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf")
    parser.add_argument("--output", default="outputs")
    parser.add_argument("--keywords", nargs="*")
    args = parser.parse_args()
    profile = profile_pdf(args.pdf, args.output, args.keywords)
    print(
        json.dumps(
            {"pdf_name": profile["pdf_name"], "relevant_pages": profile["relevant_pages"]},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
