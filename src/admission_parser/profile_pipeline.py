from __future__ import annotations

import argparse
import json
from pathlib import Path

from .chunker import chunk_markdown
from .category_router import category_counts, categorize_chunk, focus_instruction
from .extractor import extract_pdf
from .llm_parser import parse_chunk_by_category
from .merger import merge_admission_infos, warning_to_structured
from .profile_filter import filter_chunks, write_filtered_chunks
from .profiler import profile_pdf
from .reporter import ApplicantProfile, build_report
from .utils import ensure_dir, write_json
from .validator import validate_admission_info


def parse_pdf_for_profile(
    pdf_path: str | Path,
    output: str | Path,
    profile: ApplicantProfile,
    profile_dir: str | Path = "outputs",
    report_output: str | Path | None = None,
    dry_run: bool = False,
) -> dict:
    pdf_path = Path(pdf_path)
    output = Path(output)
    profile_dir = ensure_dir(profile_dir)

    page_profile = profile_pdf(pdf_path, profile_dir)
    pages = page_profile["relevant_pages"] or None
    extracted_pages = extract_pdf(pdf_path, pages=pages)
    markdown = "\n\n---\n\n".join(page.markdown for page in extracted_pages)
    chunks = chunk_markdown(markdown, pdf_path.name)
    filtered_chunks, decisions = filter_chunks(chunks, profile)

    stem = output.stem
    write_filtered_chunks(
        chunks,
        decisions,
        profile_dir / f"{stem}_profile_chunks.json",
        profile_dir / f"{stem}_profile_chunk_decisions.json",
    )

    if dry_run:
        payload = {
            "_profile": {
                "targets": profile.targets,
                "english_test": profile.english_test,
                "background": profile.background,
                "source_chunks": len(chunks),
                "selected_chunks": len(filtered_chunks),
                "category_counts": category_counts(filtered_chunks),
            },
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
        "targets": profile.targets,
        "english_test": profile.english_test,
        "background": profile.background,
        "source_chunks": len(chunks),
        "selected_chunks": len(filtered_chunks),
        "category_counts": category_counts(filtered_chunks),
    }
    write_json(output, payload)

    if report_output:
        Path(report_output).write_text(build_report(payload, profile), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf")
    parser.add_argument("--output", default=None)
    parser.add_argument("--report-output", default=None)
    parser.add_argument("--profile-dir", default="outputs")
    parser.add_argument("--target", action="append", default=[])
    parser.add_argument("--english-test", default="")
    parser.add_argument("--dry-run", action="store_true", help="Only filter chunks; do not call the LLM.")
    parser.add_argument(
        "--background",
        default="",
        choices=["", "cn_undergrad", "jp_undergrad", "overseas_undergrad"],
    )
    args = parser.parse_args()

    output = args.output or str(ensure_dir("outputs") / f"{Path(args.pdf).stem}_personal.json")
    profile = ApplicantProfile(
        targets=args.target,
        english_test=args.english_test,
        background=args.background,
    )
    payload = parse_pdf_for_profile(
        args.pdf,
        output=output,
        profile=profile,
        profile_dir=args.profile_dir,
        report_output=args.report_output,
        dry_run=args.dry_run,
    )
    print(
        json.dumps(
            {
                "output": output,
                "report_output": args.report_output,
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
