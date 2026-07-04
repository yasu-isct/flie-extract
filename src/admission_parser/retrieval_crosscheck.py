from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .category_router import categorize_chunk
from .chunker import TextChunk
from .profile_input import add_profile_arguments, profile_from_args
from .utils import ensure_dir
from .vector_retriever import (
    EmbeddingModel,
    build_profile_queries,
    load_chunks,
    retrieve_chunks,
)


def _decision_by_index(decisions: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {int(decision["index"]): decision for decision in decisions}


def _chunk_record(
    chunks: list[TextChunk],
    index: int,
    ngram_decision: dict[str, Any] | None,
    embedding_decision: dict[str, Any] | None,
) -> dict[str, Any]:
    chunk = chunks[index]
    ngram_queries = ngram_decision.get("matched_queries", []) if ngram_decision else []
    embedding_queries = embedding_decision.get("matched_queries", []) if embedding_decision else []
    return {
        "index": index,
        "pdf_name": chunk.pdf_name,
        "pages": chunk.page_numbers,
        "title": chunk.title,
        "category": categorize_chunk(chunk),
        "text_preview": " ".join(chunk.text.split())[:300],
        "ngram_score": ngram_decision.get("score") if ngram_decision else None,
        "embedding_score": embedding_decision.get("score") if embedding_decision else None,
        "ngram_matched_queries": ngram_queries,
        "embedding_matched_queries": embedding_queries,
    }


def compare_retrieval_backends(
    chunks: list[TextChunk],
    queries: list[str],
    top_k: int = 30,
    per_query_k: int = 6,
    embedding_model_path: str | Path | None = None,
    embedding_cache_dir: str | Path | None = None,
    embedding_model: EmbeddingModel | None = None,
) -> dict[str, Any]:
    _ngram_chunks, ngram_decisions = retrieve_chunks(
        chunks,
        queries,
        top_k=top_k,
        per_query_k=per_query_k,
        backend="ngram",
    )
    _embedding_chunks, embedding_decisions = retrieve_chunks(
        chunks,
        queries,
        top_k=top_k,
        per_query_k=per_query_k,
        backend="local-embedding",
        embedding_model_path=embedding_model_path,
        embedding_cache_dir=embedding_cache_dir,
        embedding_model=embedding_model,
    )

    ngram_by_index = _decision_by_index(ngram_decisions)
    embedding_by_index = _decision_by_index(embedding_decisions)
    ngram_indexes = set(ngram_by_index)
    embedding_indexes = set(embedding_by_index)
    overlap = sorted(ngram_indexes & embedding_indexes)
    only_ngram = sorted(ngram_indexes - embedding_indexes)
    only_embedding = sorted(embedding_indexes - ngram_indexes)
    union = ngram_indexes | embedding_indexes

    return {
        "summary": {
            "source_chunks": len(chunks),
            "queries": len(queries),
            "top_k": top_k,
            "per_query_k": per_query_k,
            "ngram_selected": len(ngram_indexes),
            "embedding_selected": len(embedding_indexes),
            "overlap": len(overlap),
            "only_ngram": len(only_ngram),
            "only_embedding": len(only_embedding),
            "jaccard": round(len(overlap) / len(union), 6) if union else 1.0,
            "embedding_model_path": str(embedding_model_path or ""),
            "embedding_cache_dir": str(embedding_cache_dir or ""),
        },
        "queries": queries,
        "overlap": [
            _chunk_record(chunks, index, ngram_by_index[index], embedding_by_index[index])
            for index in overlap
        ],
        "only_ngram": [
            _chunk_record(chunks, index, ngram_by_index[index], None) for index in only_ngram
        ],
        "only_embedding": [
            _chunk_record(chunks, index, None, embedding_by_index[index])
            for index in only_embedding
        ],
        "ngram_decisions": ngram_decisions,
        "embedding_decisions": embedding_decisions,
    }


def write_crosscheck_json(payload: dict[str, Any], output: str | Path) -> None:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _markdown_chunk_list(title: str, rows: list[dict[str, Any]]) -> list[str]:
    lines = [f"## {title}", ""]
    if not rows:
        lines.extend(["None.", ""])
        return lines
    for item in rows:
        pages = ",".join(str(page) for page in item["pages"]) or "-"
        ngram_score = "-" if item["ngram_score"] is None else f"{item['ngram_score']:.6g}"
        embedding_score = (
            "-" if item["embedding_score"] is None else f"{item['embedding_score']:.6g}"
        )
        lines.extend(
            [
                f"### #{item['index']} {item['title'] or '(untitled)'}",
                "",
                f"- pages: {pages}",
                f"- category: {item['category']}",
                f"- ngram_score: {ngram_score}",
                f"- embedding_score: {embedding_score}",
                f"- preview: {item['text_preview']}",
                "",
            ]
        )
    return lines


def write_crosscheck_markdown(payload: dict[str, Any], output: str | Path) -> None:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    summary = payload["summary"]
    lines = [
        "# Retrieval Crosscheck",
        "",
        "## Summary",
        "",
        f"- source_chunks: {summary['source_chunks']}",
        f"- queries: {summary['queries']}",
        f"- top_k: {summary['top_k']}",
        f"- per_query_k: {summary['per_query_k']}",
        f"- ngram_selected: {summary['ngram_selected']}",
        f"- embedding_selected: {summary['embedding_selected']}",
        f"- overlap: {summary['overlap']}",
        f"- only_ngram: {summary['only_ngram']}",
        f"- only_embedding: {summary['only_embedding']}",
        f"- jaccard: {summary['jaccard']}",
        "",
    ]
    lines.extend(_markdown_chunk_list("Overlap", payload["overlap"]))
    lines.extend(_markdown_chunk_list("Only Ngram", payload["only_ngram"]))
    lines.extend(_markdown_chunk_list("Only Embedding", payload["only_embedding"]))
    output.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run ngram and local-embedding retrieval on the same chunks and compare results."
    )
    parser.add_argument("chunks_json")
    parser.add_argument("--top-k", type=int, default=30)
    parser.add_argument("--per-query-k", type=int, default=6)
    parser.add_argument("--embedding-model-path", default=None)
    parser.add_argument("--embedding-cache-dir", default=str(Path("outputs") / "embedding_cache"))
    parser.add_argument("--output", default=None)
    parser.add_argument("--markdown-output", default=None)
    add_profile_arguments(parser)
    args = parser.parse_args()

    profile = profile_from_args(args)
    chunks = load_chunks(args.chunks_json)
    queries = build_profile_queries(profile)
    payload = compare_retrieval_backends(
        chunks,
        queries,
        top_k=args.top_k,
        per_query_k=args.per_query_k,
        embedding_model_path=args.embedding_model_path,
        embedding_cache_dir=args.embedding_cache_dir,
    )
    chunks_path = Path(args.chunks_json)
    output = Path(args.output) if args.output else chunks_path.with_name("retrieval_crosscheck.json")
    markdown_output = (
        Path(args.markdown_output)
        if args.markdown_output
        else chunks_path.with_name("retrieval_crosscheck.md")
    )
    write_crosscheck_json(payload, output)
    write_crosscheck_markdown(payload, markdown_output)
    print(
        json.dumps(
            {
                **payload["summary"],
                "output": str(output),
                "markdown_output": str(markdown_output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
