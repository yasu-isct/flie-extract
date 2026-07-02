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
from .user_requirements import build_user_requirements
from .utils import (
    DIAGNOSTICS_DIR,
    FINAL_JSON_DIR,
    FINAL_REPORTS_DIR,
    INTERMEDIATE_DIR,
    ensure_dir,
    write_json,
)
from .validator import validate_admission_info
from .vector_retriever import build_profile_queries, retrieve_chunks, write_retrieval_outputs

CATEGORY_MINIMUMS = {
    "periods": 4,
    "documents": 8,
    "english": 5,
    "fees": 4,
    "methods": 3,
    "exams": 8,
    "general": 4,
}

CATEGORY_MAXIMUMS = {
    "periods": 8,
    "documents": 14,
    "english": 8,
    "fees": 6,
    "methods": 5,
    "exams": 12,
    "general": 10,
}


def _chunk_key(chunk) -> tuple:
    return (chunk.pdf_name, tuple(chunk.page_numbers), chunk.title, chunk.text)


def _merge_and_balance_chunks(base_chunks, supplement_chunks):
    merged = []
    seen = set()
    for chunk in [*base_chunks, *supplement_chunks]:
        key = _chunk_key(chunk)
        if key in seen:
            continue
        seen.add(key)
        merged.append(chunk)

    by_category = {}
    for chunk in merged:
        by_category.setdefault(categorize_chunk(chunk), []).append(chunk)

    selected = []
    selected_keys = set()

    for category, minimum in CATEGORY_MINIMUMS.items():
        for chunk in by_category.get(category, [])[:minimum]:
            key = _chunk_key(chunk)
            if key not in selected_keys:
                selected.append(chunk)
                selected_keys.add(key)

    for category, chunks in by_category.items():
        maximum = CATEGORY_MAXIMUMS.get(category, 8)
        already = sum(1 for chunk in selected if categorize_chunk(chunk) == category)
        for chunk in chunks:
            if already >= maximum:
                break
            key = _chunk_key(chunk)
            if key in selected_keys:
                continue
            selected.append(chunk)
            selected_keys.add(key)
            already += 1

    return selected


def parse_pdf_for_profile(
    pdf_path: str | Path,
    output: str | Path,
    profile: ApplicantProfileV2,
    profile_dir: str | Path = INTERMEDIATE_DIR,
    diagnostics_dir: str | Path = DIAGNOSTICS_DIR,
    report_output: str | Path | None = None,
    dry_run: bool = False,
    page_scope: str = "all",
    retrieval_mode: str = "hybrid",
    top_k: int = 30,
    run_dir: str | Path | None = None,
) -> dict:
    pdf_path = Path(pdf_path)
    if run_dir:
        run_dir = ensure_dir(run_dir)
        profile_dir = ensure_dir(run_dir)
        diagnostics_dir = ensure_dir(run_dir)
        output = Path(output)
        report_output = Path(report_output) if report_output else None
    else:
        output = Path(output)
        profile_dir = ensure_dir(profile_dir)
        diagnostics_dir = ensure_dir(diagnostics_dir)

    page_profile = profile_pdf(pdf_path, profile_dir)
    if run_dir:
        write_json(
            Path(run_dir) / "01_page_profile_summary.json",
            {
                "pdf_name": page_profile.get("pdf_name"),
                "keywords": page_profile.get("keywords", []),
                "relevant_pages": page_profile.get("relevant_pages", []),
                "page_scope": page_scope,
            },
        )
    pages = (page_profile["relevant_pages"] or None) if page_scope == "relevant" else None
    extracted_pages = extract_pdf(pdf_path, pages=pages)
    markdown = "\n\n---\n\n".join(page.markdown for page in extracted_pages)
    chunks = chunk_markdown(markdown, pdf_path.name)
    if run_dir:
        (Path(run_dir) / "02_clean.md").write_text(markdown, encoding="utf-8")
        write_json(Path(run_dir) / "03_chunks.json", [chunk.__dict__ for chunk in chunks])
    cursor = build_cursor(profile)
    cursor_chunks, decisions = select_chunks_by_cursor(chunks, cursor)

    stem = output.stem
    write_cursor_outputs(
        chunks,
        decisions,
        diagnostics_dir / ("04_cursor_chunks.json" if run_dir else f"{stem}_cursor_chunks.json"),
        diagnostics_dir / ("04_cursor_decisions.json" if run_dir else f"{stem}_cursor_decisions.json"),
    )
    retrieval_queries: list[str] = []
    retrieval_decisions: list[dict] = []
    if retrieval_mode in {"vector", "hybrid"}:
        retrieval_queries = build_profile_queries(profile)
        retrieval_source = chunks if retrieval_mode == "hybrid" else cursor_chunks
        retrieved_chunks, retrieval_decisions = retrieve_chunks(retrieval_source, retrieval_queries, top_k=top_k)
        if retrieval_mode == "hybrid":
            filtered_chunks = _merge_and_balance_chunks(cursor_chunks, retrieved_chunks)
        else:
            filtered_chunks = retrieved_chunks
        write_retrieval_outputs(
            retrieved_chunks,
            retrieval_decisions,
            diagnostics_dir / ("05_retrieved_chunks.json" if run_dir else f"{stem}_retrieved_chunks.json"),
            diagnostics_dir / ("05_retrieval_decisions.json" if run_dir else f"{stem}_retrieval_decisions.json"),
            retrieval_queries,
        )
    else:
        filtered_chunks = cursor_chunks

    if dry_run:
        payload = {
            "_profile": {
                **profile.model_dump(),
                "source_chunks": len(chunks),
                "cursor_chunks": len(cursor_chunks),
                "selected_chunks": len(filtered_chunks),
                "category_counts": category_counts(filtered_chunks),
                "page_scope": page_scope,
                "retrieval_mode": retrieval_mode,
                "retrieval_queries": len(retrieval_queries),
            },
            "_cursor": cursor.model_dump(),
            "_retrieval": {
                "queries": retrieval_queries,
                "decisions": retrieval_decisions,
            },
            "selected_chunk_titles": [chunk.title for chunk in filtered_chunks[:50]],
        }
        if run_dir:
            output = Path(run_dir) / "06_dry_run_summary.json"
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
        "cursor_chunks": len(cursor_chunks),
        "selected_chunks": len(filtered_chunks),
        "category_counts": category_counts(filtered_chunks),
        "page_scope": page_scope,
        "retrieval_mode": retrieval_mode,
        "retrieval_queries": len(retrieval_queries),
    }
    payload["_cursor"] = cursor.model_dump()
    payload["_retrieval"] = {
        "queries": retrieval_queries,
        "decisions": retrieval_decisions,
    }
    payload["_user_requirements"] = build_user_requirements(payload, profile)
    if run_dir:
        output = Path(run_dir) / "06_structured.json"
        report_output = Path(run_dir) / "07_report.md"
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
    parser.add_argument("--page-scope", choices=["all", "relevant"], default="all")
    parser.add_argument("--retrieval-mode", choices=["none", "vector", "hybrid"], default="hybrid")
    parser.add_argument("--top-k", type=int, default=30)
    parser.add_argument("--run-dir", default=None, help="Write ordered run artifacts into one directory.")
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
        page_scope=args.page_scope,
        retrieval_mode=args.retrieval_mode,
        top_k=args.top_k,
        run_dir=args.run_dir,
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
