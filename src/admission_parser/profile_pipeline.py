from __future__ import annotations

import argparse
import json
from pathlib import Path

from .chunker import chunk_markdown
from .category_router import category_counts, categorize_chunk, focus_instruction
from .cursor_selector import build_cursor, select_chunks_by_cursor, write_cursor_outputs
from .extractor import extract_pdf
from .llm_parser import parse_chunk_by_category
from .merger import merge_admission_infos, warning_to_structured
from .profile_input import ApplicantProfileV2, add_profile_arguments, profile_from_args
from .profiler import profile_pdf
from .reporter import build_report
from .utils import (
    DIAGNOSTICS_DIR,
    FINAL_JSON_DIR,
    FINAL_REPORTS_DIR,
    INTERMEDIATE_DIR,
    ensure_dir,
    write_json,
)
from .validator import validate_admission_info


def parse_pdf_for_profile(
    pdf_path: str | Path,
    output: str | Path,
    profile: ApplicantProfileV2,
    profile_dir: str | Path = INTERMEDIATE_DIR,
    diagnostics_dir: str | Path = DIAGNOSTICS_DIR,
    report_output: str | Path | None = None,
    dry_run: bool = False,
) -> dict:
    pdf_path = Path(pdf_path)
    output = Path(output)
    profile_dir = ensure_dir(profile_dir)
    diagnostics_dir = ensure_dir(diagnostics_dir)

    page_profile = profile_pdf(pdf_path, profile_dir)
    pages = page_profile["relevant_pages"] or None
    extracted_pages = extract_pdf(pdf_path, pages=pages)
    markdown = "\n\n---\n\n".join(page.markdown for page in extracted_pages)
    chunks = chunk_markdown(markdown, pdf_path.name)
    cursor = build_cursor(profile)
    filtered_chunks, decisions = select_chunks_by_cursor(chunks, cursor)

    stem = output.stem
    write_cursor_outputs(
        chunks,
        decisions,
        diagnostics_dir / f"{stem}_cursor_chunks.json",
        diagnostics_dir / f"{stem}_cursor_decisions.json",
    )

    if dry_run:
        payload = {
            "_profile": {
                **profile.model_dump(),
                "source_chunks": len(chunks),
                "selected_chunks": len(filtered_chunks),
                "category_counts": category_counts(filtered_chunks),
            },
            "_cursor": cursor.model_dump(),
            "selected_chunk_titles": [chunk.title for chunk in filtered_chunks[:50]],
        }
        write_json(output, payload)
        return payload

    partials = []
    for chunk in filtered_chunks:
        category = categorize_chunk(chunk)
        partials.append(
            parse_chunk_by_category(
                chunk,
                category=category,
                focus=focus_instruction(category),
            )
        )
    merged = merge_admission_infos(partials)
    errors = validate_admission_info(merged)
    if errors:
        merged.warnings.extend(errors)
        merged.structured_warnings.extend(warning_to_structured(error) for error in errors)

    payload = merged.model_dump(mode="json")
    payload["_profile"] = {
        **profile.model_dump(),
        "source_chunks": len(chunks),
        "selected_chunks": len(filtered_chunks),
        "category_counts": category_counts(filtered_chunks),
    }
    payload["_cursor"] = cursor.model_dump()
    write_json(output, payload)

    if report_output:
        Path(report_output).write_text(build_report(payload, profile.to_report_profile()), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf")
    parser.add_argument("--output", default=None)
    parser.add_argument("--report-output", default=None)
    parser.add_argument("--profile-dir", default=str(INTERMEDIATE_DIR))
    parser.add_argument("--diagnostics-dir", default=str(DIAGNOSTICS_DIR))
    parser.add_argument("--dry-run", action="store_true", help="Only filter chunks; do not call the LLM.")
    add_profile_arguments(parser)
    args = parser.parse_args()

    if args.output:
        output = args.output
    elif args.dry_run:
        output = str(ensure_dir(DIAGNOSTICS_DIR) / f"{Path(args.pdf).stem}_profile_dry_run.json")
    else:
        output = str(ensure_dir(FINAL_JSON_DIR) / f"{Path(args.pdf).stem}_personal.json")
    report_output = args.report_output
    if not report_output and not args.dry_run:
        report_output = str(ensure_dir(FINAL_REPORTS_DIR) / f"{Path(output).stem}_report.md")
    profile = profile_from_args(args)
    payload = parse_pdf_for_profile(
        args.pdf,
        output=output,
        profile=profile,
        profile_dir=args.profile_dir,
        diagnostics_dir=args.diagnostics_dir,
        report_output=report_output,
        dry_run=args.dry_run,
    )
    print(
        json.dumps(
            {
                "output": output,
                "report_output": report_output,
                "source_chunks": payload.get("_profile", {}).get("source_chunks"),
                "selected_chunks": payload.get("_profile", {}).get("selected_chunks"),
                "warnings": len(payload.get("warnings", [])),
            },
            ensure_ascii=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
