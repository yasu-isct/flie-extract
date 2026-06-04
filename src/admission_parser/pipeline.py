from __future__ import annotations

import argparse
import json
from pathlib import Path

from .chunker import chunk_markdown
from .extractor import extract_pdf
from .llm_parser import parse_chunks
from .merger import merge_admission_infos, warning_to_structured
from .profiler import profile_pdf
from .utils import FINAL_JSON_DIR, INTERMEDIATE_DIR, ensure_dir, write_json
from .validator import validate_admission_info


def parse_pdf(
    pdf_path: str | Path,
    output: str | Path,
    profile_dir: str | Path = INTERMEDIATE_DIR,
) -> dict:
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
        merged.structured_warnings.extend(warning_to_structured(error) for error in errors)
    payload = merged.model_dump(mode="json")
    write_json(output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf")
    parser.add_argument("--output", default=None)
    parser.add_argument("--profile-dir", default=str(INTERMEDIATE_DIR))
    args = parser.parse_args()
    output = args.output or str(ensure_dir(FINAL_JSON_DIR) / f"{Path(args.pdf).stem}.json")
    payload = parse_pdf(args.pdf, output=output, profile_dir=args.profile_dir)
    print(json.dumps({"output": output, "warnings": payload.get("warnings", [])}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
