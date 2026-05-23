from __future__ import annotations

import argparse
import json
from pathlib import Path

from .chunker import chunk_markdown
from .extractor import extract_pdf
from .llm_parser import parse_chunks
from .merger import merge_admission_infos
from .profiler import profile_pdf
from .utils import ensure_dir, write_json
from .validator import validate_admission_info


def parse_pdf(pdf_path: str | Path, output: str | Path, profile_dir: str | Path = "outputs") -> dict:
    pdf_path = Path(pdf_path)
    profile = profile_pdf(pdf_path, profile_dir)
    pages = profile["relevant_pages"] or None
    extracted_pages = extract_pdf(pdf_path, pages=pages)
    markdown = "\n\n---\n\n".join(page.markdown for page in extracted_pages)
    chunks = chunk_markdown(markdown, pdf_path.name)
    partials = parse_chunks(chunks)
    merged = merge_admission_infos(partials)
    errors = validate_admission_info(merged)
    if errors:
        merged.warnings.extend(errors)
    payload = merged.model_dump(mode="json")
    write_json(output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf")
    parser.add_argument("--output", default=None)
    parser.add_argument("--profile-dir", default="outputs")
    args = parser.parse_args()
    output = args.output or str(ensure_dir("outputs") / f"{Path(args.pdf).stem}.json")
    payload = parse_pdf(args.pdf, output=output, profile_dir=args.profile_dir)
    print(json.dumps({"output": output, "warnings": payload.get("warnings", [])}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
