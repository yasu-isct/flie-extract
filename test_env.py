from __future__ import annotations

import argparse
import os
from pathlib import Path

import fitz
import pdfplumber
from dotenv import load_dotenv


def check_pdf(pdf_path: str | Path) -> None:
    pdf_path = Path(pdf_path)
    doc = fitz.open(pdf_path)
    print(f"PyMuPDF pages: {len(doc)}")
    with pdfplumber.open(pdf_path) as pdf:
        print(f"pdfplumber pages: {len(pdf.pages)}")
        first = pdf.pages[0]
        text = first.extract_text() or ""
        tables = first.extract_tables() or []
        print(f"first page text chars: {len(text)}")
        print(f"first page tables: {len(tables)}")


def check_llm() -> None:
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY is not set; skip LLM connectivity check.")
        return
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    models = client.models.list()
    first_model = models.data[0].id if models.data else "<none>"
    print(f"LLM connectivity OK. First model: {first_model}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf")
    parser.add_argument("--check-llm", action="store_true")
    args = parser.parse_args()
    check_pdf(args.pdf)
    if args.check_llm:
        check_llm()


if __name__ == "__main__":
    main()
