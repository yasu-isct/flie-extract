from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

from .category_router import categorize_chunk
from .chunker import TextChunk
from .profile_input import add_profile_arguments, profile_from_args
from .vector_retriever import (
    EmbeddingModel,
    build_profile_queries,
    load_chunks,
    retrieve_chunks,
)


def _decision_by_index(decisions: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {int(decision["index"]): decision for decision in decisions}


def _indexes_by_query(decisions: list[dict[str, Any]]) -> dict[str, set[int]]:
    query_indexes: dict[str, set[int]] = {}
    for decision in decisions:
        index = int(decision["index"])
        for query in decision.get("matched_queries", []):
            query_indexes.setdefault(str(query), set()).add(index)
    return query_indexes


def _category_summary(
    chunks: list[TextChunk],
    ngram_indexes: set[int],
    embedding_indexes: set[int],
) -> dict[str, dict[str, int]]:
    categories = sorted({categorize_chunk(chunk) for chunk in chunks})
    summary: dict[str, dict[str, int]] = {}
    for category in categories:
        category_indexes = {
            index for index, chunk in enumerate(chunks) if categorize_chunk(chunk) == category
        }
        ngram = ngram_indexes & category_indexes
        embedding = embedding_indexes & category_indexes
        overlap = ngram & embedding
        summary[category] = {
            "source_chunks": len(category_indexes),
            "ngram_selected": len(ngram),
            "embedding_selected": len(embedding),
            "overlap": len(overlap),
            "only_ngram": len(ngram - embedding),
            "only_embedding": len(embedding - ngram),
        }
    return summary


def _query_summary(
    queries: list[str],
    ngram_decisions: list[dict[str, Any]],
    embedding_decisions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ngram_by_query = _indexes_by_query(ngram_decisions)
    embedding_by_query = _indexes_by_query(embedding_decisions)
    rows = []
    for query in queries:
        ngram = ngram_by_query.get(query, set())
        embedding = embedding_by_query.get(query, set())
        overlap = ngram & embedding
        union = ngram | embedding
        rows.append(
            {
                "query": query,
                "ngram_hits": len(ngram),
                "embedding_hits": len(embedding),
                "overlap": len(overlap),
                "only_ngram": len(ngram - embedding),
                "only_embedding": len(embedding - ngram),
                "jaccard": round(len(overlap) / len(union), 6) if union else 1.0,
            }
        )
    return rows


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
    category_summary = _category_summary(chunks, ngram_indexes, embedding_indexes)
    query_summary = _query_summary(queries, ngram_decisions, embedding_decisions)

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
        "category_summary": category_summary,
        "query_summary": query_summary,
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


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    lines.append("")
    return lines


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
                f"- ngram_queries: {len(item['ngram_matched_queries'])}",
                f"- embedding_queries: {len(item['embedding_matched_queries'])}",
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
    lines.extend(
        _markdown_table(
            ["category", "source", "ngram", "embedding", "overlap", "only_ngram", "only_embedding"],
            [
                [
                    category,
                    row["source_chunks"],
                    row["ngram_selected"],
                    row["embedding_selected"],
                    row["overlap"],
                    row["only_ngram"],
                    row["only_embedding"],
                ]
                for category, row in payload["category_summary"].items()
            ],
        )
    )
    lines.extend(
        _markdown_table(
            ["query", "ngram", "embedding", "overlap", "only_ngram", "only_embedding", "jaccard"],
            [
                [
                    row["query"],
                    row["ngram_hits"],
                    row["embedding_hits"],
                    row["overlap"],
                    row["only_ngram"],
                    row["only_embedding"],
                    row["jaccard"],
                ]
                for row in payload["query_summary"]
            ],
        )
    )
    lines.extend(_markdown_chunk_list("Overlap", payload["overlap"]))
    lines.extend(_markdown_chunk_list("Only Ngram", payload["only_ngram"]))
    lines.extend(_markdown_chunk_list("Only Embedding", payload["only_embedding"]))
    output.write_text("\n".join(lines), encoding="utf-8")


def _html_metric(label: str, value: Any) -> str:
    return f'<div class="metric"><span>{html.escape(label)}</span><strong>{html.escape(str(value))}</strong></div>'


def _html_table(headers: list[str], rows: list[list[Any]]) -> str:
    head = "".join(f"<th>{html.escape(str(header))}</th>" for header in headers)
    body = []
    for row in rows:
        cells = "".join(f"<td>{html.escape(str(value))}</td>" for value in row)
        body.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _html_chunk_cards(title: str, rows: list[dict[str, Any]], class_name: str) -> str:
    if not rows:
        return f"<section><h2>{html.escape(title)}</h2><p>None.</p></section>"
    cards = []
    for item in rows:
        pages = ",".join(str(page) for page in item["pages"]) or "-"
        ngram_score = "-" if item["ngram_score"] is None else f"{item['ngram_score']:.6g}"
        embedding_score = "-" if item["embedding_score"] is None else f"{item['embedding_score']:.6g}"
        cards.append(
            f'<article class="chunk-card {class_name}">'
            f"<h3>#{item['index']} {html.escape(item['title'] or '(untitled)')}</h3>"
            f"<dl>"
            f"<dt>pages</dt><dd>{html.escape(pages)}</dd>"
            f"<dt>category</dt><dd>{html.escape(item['category'])}</dd>"
            f"<dt>ngram</dt><dd>{ngram_score}</dd>"
            f"<dt>embedding</dt><dd>{embedding_score}</dd>"
            f"<dt>ngram queries</dt><dd>{len(item['ngram_matched_queries'])}</dd>"
            f"<dt>embedding queries</dt><dd>{len(item['embedding_matched_queries'])}</dd>"
            f"</dl>"
            f"<p>{html.escape(item['text_preview'])}</p>"
            f"</article>"
        )
    return f"<section><h2>{html.escape(title)}</h2>{''.join(cards)}</section>"


def write_crosscheck_html(payload: dict[str, Any], output: str | Path) -> None:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    summary = payload["summary"]
    metrics = "".join(
        [
            _html_metric("source chunks", summary["source_chunks"]),
            _html_metric("queries", summary["queries"]),
            _html_metric("ngram selected", summary["ngram_selected"]),
            _html_metric("embedding selected", summary["embedding_selected"]),
            _html_metric("overlap", summary["overlap"]),
            _html_metric("only ngram", summary["only_ngram"]),
            _html_metric("only embedding", summary["only_embedding"]),
            _html_metric("jaccard", summary["jaccard"]),
        ]
    )
    category_table = _html_table(
        ["category", "source", "ngram", "embedding", "overlap", "only_ngram", "only_embedding"],
        [
            [
                category,
                row["source_chunks"],
                row["ngram_selected"],
                row["embedding_selected"],
                row["overlap"],
                row["only_ngram"],
                row["only_embedding"],
            ]
            for category, row in payload["category_summary"].items()
        ],
    )
    query_table = _html_table(
        ["query", "ngram", "embedding", "overlap", "only_ngram", "only_embedding", "jaccard"],
        [
            [
                row["query"],
                row["ngram_hits"],
                row["embedding_hits"],
                row["overlap"],
                row["only_ngram"],
                row["only_embedding"],
                row["jaccard"],
            ]
            for row in payload["query_summary"]
        ],
    )
    body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Retrieval Crosscheck</title>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; color: #202124; background: #f6f8fb; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 28px 22px 48px; }}
    h1 {{ margin: 0 0 16px; font-size: 28px; letter-spacing: 0; }}
    h2 {{ margin: 30px 0 12px; font-size: 20px; letter-spacing: 0; }}
    h3 {{ margin: 0 0 10px; font-size: 15px; letter-spacing: 0; }}
    .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }}
    .metric {{ background: #fff; border: 1px solid #d8dee8; border-radius: 8px; padding: 12px; }}
    .metric span {{ display: block; color: #697386; font-size: 12px; margin-bottom: 6px; }}
    .metric strong {{ font-size: 18px; }}
    .table-panel {{ background: #fff; border: 1px solid #d8dee8; border-radius: 8px; overflow: auto; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 9px 10px; border-bottom: 1px solid #e5e9f0; text-align: left; vertical-align: top; }}
    th {{ background: #edf1f6; font-weight: 700; }}
    .chunk-card {{ background: #fff; border: 1px solid #d8dee8; border-left-width: 5px; border-radius: 8px; padding: 12px 14px; margin: 10px 0; }}
    .overlap {{ border-left-color: #2f7d59; }}
    .only-ngram {{ border-left-color: #9a6a21; }}
    .only-embedding {{ border-left-color: #235f9f; }}
    dl {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 6px 12px; margin: 0 0 10px; }}
    dt {{ color: #697386; font-size: 12px; }}
    dd {{ margin: 0; font-weight: 700; }}
    p {{ margin: 0; line-height: 1.5; }}
  </style>
</head>
<body>
<main>
  <h1>Retrieval Crosscheck</h1>
  <div class="metrics">{metrics}</div>
  <h2>Category Summary</h2>
  <div class="table-panel">{category_table}</div>
  <h2>Query Summary</h2>
  <div class="table-panel">{query_table}</div>
  {_html_chunk_cards("Overlap", payload["overlap"], "overlap")}
  {_html_chunk_cards("Only Ngram", payload["only_ngram"], "only-ngram")}
  {_html_chunk_cards("Only Embedding", payload["only_embedding"], "only-embedding")}
</main>
</body>
</html>
"""
    output.write_text(body, encoding="utf-8")


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
    parser.add_argument("--html-output", default=None)
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
    html_output = (
        Path(args.html_output) if args.html_output else chunks_path.with_name("retrieval_crosscheck.html")
    )
    write_crosscheck_json(payload, output)
    write_crosscheck_markdown(payload, markdown_output)
    write_crosscheck_html(payload, html_output)
    print(
        json.dumps(
            {
                **payload["summary"],
                "output": str(output),
                "markdown_output": str(markdown_output),
                "html_output": str(html_output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
