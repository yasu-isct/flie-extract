from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

from .applicability import evaluate_applicability, generate_narrative_report
from .chunker import chunk_markdown
from .category_router import category_counts, categorize_chunk, focus_instruction
from .cursor_selector import build_cursor, select_chunks_by_cursor, write_cursor_outputs
from .document_index import build_document_index, write_document_index
from .extractor import extract_pdf
from .llm_parser import combine_chunks_for_category, parse_category_batch, parse_chunk_by_category
from .merger import merge_admission_infos, warning_to_structured
from .profile_input import ApplicantProfileV2, add_profile_arguments, profile_from_args
from .profiler import profile_pdf
from .recursive_retriever import expand_chunks_by_references, write_reference_expansion
from .reference_resolver import resolve_references, write_reference_links
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


def _group_chunks_by_category(chunks):
    grouped = {}
    for chunk in chunks:
        grouped.setdefault(categorize_chunk(chunk), []).append(chunk)
    return grouped


def _llm_batch_manifest(grouped_chunks, max_batch_chars: int) -> list[dict]:
    manifest = []
    for category, chunks in sorted(grouped_chunks.items()):
        batches = combine_chunks_for_category(chunks, category=category, max_chars=max_batch_chars)
        for index, batch in enumerate(batches, start=1):
            manifest.append(
                {
                    "category": category,
                    "batch_index": index,
                    "pages": batch.page_numbers,
                    "chars": len(batch.text),
                    "source_chunks": len(chunks),
                }
            )
    return manifest


def _parse_chunks_by_category_batches(
    chunks,
    max_workers: int,
    max_batch_chars: int,
    llm_cache_dir: str | Path | None = None,
) -> tuple[list, dict[str, int]]:
    grouped = _group_chunks_by_category(chunks)
    partials = []
    cache_stats = {"hits": 0, "misses": 0}
    cache_lock = Lock()

    def parse_with_cache_stats(category_chunks, category):
        local_stats = {"hits": 0, "misses": 0}
        result = parse_category_batch(
            category_chunks,
            category,
            None,
            focus_instruction(category),
            max_batch_chars,
            cache_dir=llm_cache_dir,
            cache_stats=local_stats,
        )
        with cache_lock:
            cache_stats["hits"] += local_stats.get("hits", 0)
            cache_stats["misses"] += local_stats.get("misses", 0)
        return result

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                parse_with_cache_stats,
                category_chunks,
                category,
            ): category
            for category, category_chunks in grouped.items()
        }
        for future in as_completed(futures):
            partials.extend(future.result())
    return partials, cache_stats


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
    llm_strategy: str = "category",
    max_workers: int | None = None,
    max_batch_chars: int = 18000,
    retrieval_backend: str = "ngram",
    embedding_model_path: str | Path | None = None,
    embedding_cache_dir: str | Path | None = None,
    retrieval_source: str = "all",
    reference_expansion: str = "none",
    reference_max_depth: int = 1,
    llm_cache_dir: str | Path | None = Path("outputs") / "llm_cache",
    applicability_pass: bool = False,
    llm_report: bool = False,
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
    document_index = build_document_index(chunks)
    reference_links = resolve_references(document_index)
    if run_dir:
        write_document_index(document_index, Path(run_dir) / "03_document_index.json")
        write_reference_links(reference_links, Path(run_dir) / "03_reference_links.json")
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
        source_chunks = chunks if retrieval_source == "all" and retrieval_mode == "hybrid" else cursor_chunks
        retrieved_chunks, retrieval_decisions = retrieve_chunks(
            source_chunks,
            retrieval_queries,
            top_k=top_k,
            backend=retrieval_backend,
            embedding_model_path=embedding_model_path,
            embedding_cache_dir=embedding_cache_dir,
        )
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

    reference_expansion_records = []
    if reference_expansion != "none":
        expansion_depth = reference_max_depth if reference_expansion == "recursive" else 1
        base_selected_count = len(filtered_chunks)
        filtered_chunks, reference_expansion_records = expand_chunks_by_references(
            chunks,
            filtered_chunks,
            reference_links,
            max_depth=expansion_depth,
        )
        if run_dir:
            write_json(
                Path(run_dir) / "05_reference_expanded_chunks.json",
                [chunk.__dict__ for chunk in filtered_chunks],
            )
            write_reference_expansion(
                reference_expansion_records,
                Path(run_dir) / "05_reference_expansion.json",
                base_selected_count=base_selected_count,
                final_selected_count=len(filtered_chunks),
            )

    if dry_run:
        grouped_chunks = _group_chunks_by_category(filtered_chunks)
        llm_batches = _llm_batch_manifest(grouped_chunks, max_batch_chars)
        payload = {
            "_profile": {
                **profile.model_dump(),
                "source_chunks": len(chunks),
                "cursor_chunks": len(cursor_chunks),
                "selected_chunks": len(filtered_chunks),
                "category_counts": category_counts(filtered_chunks),
                "page_scope": page_scope,
                "retrieval_mode": retrieval_mode,
                "retrieval_backend": retrieval_backend,
                "retrieval_source": retrieval_source,
                "reference_expansion": reference_expansion,
                "reference_max_depth": reference_max_depth,
                "reference_links": len(reference_links),
                "reference_expanded_chunks": len(reference_expansion_records),
                "embedding_model_path": str(embedding_model_path or os.getenv("LOCAL_EMBEDDING_MODEL_PATH", "")),
                "embedding_cache_dir": str(embedding_cache_dir or ""),
                "retrieval_queries": len(retrieval_queries),
                "llm_strategy": llm_strategy,
                "estimated_llm_requests": len(filtered_chunks) if llm_strategy == "chunk" else len(llm_batches),
                "max_workers": max_workers or int(os.getenv("LLM_MAX_WORKERS", "4")),
                "max_batch_chars": max_batch_chars,
            },
            "_cursor": cursor.model_dump(),
            "_retrieval": {
                "queries": retrieval_queries,
                "decisions": retrieval_decisions,
            },
            "_llm_batches": llm_batches,
            "selected_chunk_titles": [chunk.title for chunk in filtered_chunks[:50]],
        }
        if run_dir:
            output = Path(run_dir) / "06_dry_run_summary.json"
            payload["_artifacts"] = {
                "dry_run_summary": str(output),
                "clean_markdown": str(Path(run_dir) / "02_clean.md"),
                "chunks": str(Path(run_dir) / "03_chunks.json"),
                "cursor_chunks": str(Path(run_dir) / "04_cursor_chunks.json"),
                "retrieved_chunks": str(Path(run_dir) / "05_retrieved_chunks.json"),
                "document_index": str(Path(run_dir) / "03_document_index.json"),
                "reference_links": str(Path(run_dir) / "03_reference_links.json"),
                "reference_expansion": str(Path(run_dir) / "05_reference_expansion.json"),
            }
        write_json(output, payload)
        return payload

    max_workers = max_workers or int(os.getenv("LLM_MAX_WORKERS", "4"))
    grouped_chunks = _group_chunks_by_category(filtered_chunks)
    llm_batches = _llm_batch_manifest(grouped_chunks, max_batch_chars)
    if run_dir:
        write_json(Path(run_dir) / "06_llm_batches.json", llm_batches)
    if llm_strategy == "category":
        partials, llm_cache_stats = _parse_chunks_by_category_batches(
            filtered_chunks,
            max_workers,
            max_batch_chars,
            llm_cache_dir=llm_cache_dir,
        )
    else:
        partials = []
        llm_cache_stats = {"hits": 0, "misses": 0}
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
        "retrieval_backend": retrieval_backend,
        "retrieval_source": retrieval_source,
        "reference_expansion": reference_expansion,
        "reference_max_depth": reference_max_depth,
        "reference_links": len(reference_links),
        "reference_expanded_chunks": len(reference_expansion_records),
        "embedding_model_path": str(embedding_model_path or os.getenv("LOCAL_EMBEDDING_MODEL_PATH", "")),
        "embedding_cache_dir": str(embedding_cache_dir or ""),
        "retrieval_queries": len(retrieval_queries),
        "llm_strategy": llm_strategy,
        "llm_requests": len(filtered_chunks) if llm_strategy == "chunk" else len(llm_batches),
        "llm_cache_dir": str(llm_cache_dir or ""),
        "llm_cache_hits": llm_cache_stats.get("hits", 0),
        "llm_cache_misses": llm_cache_stats.get("misses", 0),
        "max_workers": max_workers,
        "max_batch_chars": max_batch_chars,
    }
    payload["_cursor"] = cursor.model_dump()
    payload["_retrieval"] = {
        "queries": retrieval_queries,
        "decisions": retrieval_decisions,
    }
    payload["_user_requirements"] = build_user_requirements(payload, profile)
    applicability_result = None
    narrative_report = None
    if applicability_pass:
        applicability_result = evaluate_applicability(
            payload,
            profile,
            cache_dir=llm_cache_dir,
        )
        payload["_applicability"] = applicability_result.model_dump(mode="json")
    if llm_report:
        narrative_report = generate_narrative_report(
            payload,
            profile,
            applicability=applicability_result or payload.get("_applicability"),
            cache_dir=llm_cache_dir,
        )
    if run_dir:
        output = Path(run_dir) / "07_structured.json"
        report_output = Path(run_dir) / "08_report.md"
        applicability_output = Path(run_dir) / "09_applicability.json"
        llm_report_output = Path(run_dir) / "10_llm_report.md"
        payload["_artifacts"] = {
            "llm_batches": str(Path(run_dir) / "06_llm_batches.json"),
            "structured_json": str(output),
            "report": str(report_output),
            "applicability": str(applicability_output) if applicability_pass else "",
            "llm_report": str(llm_report_output) if llm_report else "",
            "clean_markdown": str(Path(run_dir) / "02_clean.md"),
            "chunks": str(Path(run_dir) / "03_chunks.json"),
            "cursor_chunks": str(Path(run_dir) / "04_cursor_chunks.json"),
            "retrieved_chunks": str(Path(run_dir) / "05_retrieved_chunks.json"),
            "document_index": str(Path(run_dir) / "03_document_index.json"),
            "reference_links": str(Path(run_dir) / "03_reference_links.json"),
            "reference_expansion": str(Path(run_dir) / "05_reference_expansion.json"),
        }
    write_json(output, payload)

    if report_output:
        Path(report_output).write_text(build_report(payload, profile.to_report_profile()), encoding="utf-8")
    if run_dir and applicability_pass and applicability_result:
        write_json(Path(run_dir) / "09_applicability.json", applicability_result.model_dump(mode="json"))
    if run_dir and llm_report and narrative_report:
        Path(run_dir, "10_llm_report.md").write_text(narrative_report.report_markdown, encoding="utf-8")
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
    parser.add_argument("--retrieval-backend", choices=["ngram", "local-embedding"], default="ngram")
    parser.add_argument("--retrieval-source", choices=["all", "cursor"], default="all")
    parser.add_argument("--reference-expansion", choices=["none", "direct", "recursive"], default="none")
    parser.add_argument("--reference-max-depth", type=int, default=1)
    parser.add_argument("--embedding-model-path", default=None)
    parser.add_argument("--embedding-cache-dir", default=str(Path("outputs") / "embedding_cache"))
    parser.add_argument("--top-k", type=int, default=30)
    parser.add_argument("--run-dir", default=None, help="Write ordered run artifacts into one directory.")
    parser.add_argument("--llm-strategy", choices=["category", "chunk"], default="category")
    parser.add_argument("--llm-cache-dir", default=str(Path("outputs") / "llm_cache"))
    parser.add_argument("--no-llm-cache", action="store_true")
    parser.add_argument("--applicability-pass", action="store_true")
    parser.add_argument("--llm-report", action="store_true")
    parser.add_argument("--max-workers", type=int, default=None)
    parser.add_argument("--max-batch-chars", type=int, default=18000)
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
        llm_strategy=args.llm_strategy,
        max_workers=args.max_workers,
        max_batch_chars=args.max_batch_chars,
        retrieval_backend=args.retrieval_backend,
        embedding_model_path=args.embedding_model_path,
        embedding_cache_dir=args.embedding_cache_dir,
        retrieval_source=args.retrieval_source,
        reference_expansion=args.reference_expansion,
        reference_max_depth=args.reference_max_depth,
        llm_cache_dir=None if args.no_llm_cache else args.llm_cache_dir,
        applicability_pass=args.applicability_pass,
        llm_report=args.llm_report,
    )
    print(
        json.dumps(
            {
                "output": output,
                "report_output": report_output,
                "artifacts": payload.get("_artifacts", {}),
                "source_chunks": payload.get("_profile", {}).get("source_chunks"),
                "selected_chunks": payload.get("_profile", {}).get("selected_chunks"),
                "llm_requests": payload.get("_profile", {}).get("llm_requests")
                or payload.get("_profile", {}).get("estimated_llm_requests"),
                "llm_cache_hits": payload.get("_profile", {}).get("llm_cache_hits"),
                "llm_cache_misses": payload.get("_profile", {}).get("llm_cache_misses"),
                "warnings": len(payload.get("warnings", [])),
            },
            ensure_ascii=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
