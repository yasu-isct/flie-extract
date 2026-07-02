from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .chunker import TextChunk
from .cursor_selector import build_cursor
from .profile_input import add_profile_arguments, profile_from_args
from .utils import DIAGNOSTICS_DIR, ensure_dir


@dataclass
class RetrievalDecision:
    index: int
    score: float
    title: str
    pages: list[int]
    matched_queries: list[str]


def _clean(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _char_ngrams(text: str, n_min: int = 2, n_max: int = 4) -> list[str]:
    text = _clean(text)
    compact = re.sub(r"\s+", "", text)
    grams: list[str] = []
    for n in range(n_min, n_max + 1):
        if len(compact) < n:
            continue
        grams.extend(compact[i : i + n] for i in range(len(compact) - n + 1))
    words = [word for word in text.split(" ") if word]
    grams.extend(words)
    return grams


def vectorize(text: str) -> dict[str, float]:
    counts: dict[str, float] = {}
    for gram in _char_ngrams(text):
        counts[gram] = counts.get(gram, 0.0) + 1.0
    norm = math.sqrt(sum(value * value for value in counts.values())) or 1.0
    return {key: value / norm for key, value in counts.items()}


def cosine(left: dict[str, float], right: dict[str, float]) -> float:
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(key, 0.0) for key, value in left.items())


def chunk_text(chunk: TextChunk) -> str:
    return f"{chunk.title}\n{chunk.text}"


def build_profile_queries(profile: Any) -> list[str]:
    cursor = build_cursor(profile)
    targets = " ".join(profile.targets)
    queries = [
        "出願期間 締切 必着 消印有効 インターネット出願",
        "提出書類 必要書類 証明書 様式 出願書類",
        "出願方法 郵送 オンライン 提出先 マイページ",
        "検定料 入学検定料 支払方法 金額 クレジットカード",
        "試験日程 筆答試験 口述試験 合格発表 受験票",
    ]
    if targets:
        queries.extend(
            [
                f"{targets} 募集人員 コース",
                f"{targets} 試験日程 筆答試験 口述試験",
                f"{targets} 志望理由 研究室 指導教員",
            ]
        )
    if cursor.english_aliases:
        queries.append(f"{' '.join(cursor.english_aliases)} スコア 直送 機関コード DIコード")
    if cursor.background_aliases:
        queries.append(f"{' '.join(cursor.background_aliases)} 出願資格 証明書 在留カード パスポート")
    if cursor.degree_aliases:
        queries.append(f"{' '.join(cursor.degree_aliases)} 入試 出願 課程")
    if cursor.exam_type_aliases:
        queries.append(f"{' '.join(cursor.exam_type_aliases)} 入試 選抜")
    return list(dict.fromkeys(query for query in queries if query.strip()))


def retrieve_chunks(
    chunks: list[TextChunk],
    queries: list[str],
    top_k: int = 30,
    per_query_k: int = 6,
) -> tuple[list[TextChunk], list[dict[str, Any]]]:
    chunk_vectors = [vectorize(chunk_text(chunk)) for chunk in chunks]
    query_vectors = [(query, vectorize(query)) for query in queries]
    scores: dict[int, float] = {}
    matched_queries: dict[int, list[str]] = {}

    for query, query_vector in query_vectors:
        ranked = sorted(
            (
                (index, cosine(query_vector, chunk_vector))
                for index, chunk_vector in enumerate(chunk_vectors)
            ),
            key=lambda item: item[1],
            reverse=True,
        )[:per_query_k]
        for index, score in ranked:
            if score <= 0:
                continue
            scores[index] = max(scores.get(index, 0.0), score)
            matched_queries.setdefault(index, []).append(query)

    selected_indexes = [
        index for index, _score in sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_k]
    ]
    selected_indexes = sorted(selected_indexes)
    decisions = [
        asdict(
            RetrievalDecision(
                index=index,
                score=round(scores[index], 6),
                title=chunks[index].title,
                pages=chunks[index].page_numbers,
                matched_queries=matched_queries.get(index, []),
            )
        )
        for index in selected_indexes
    ]
    return [chunks[index] for index in selected_indexes], decisions


def retrieve_chunk_indexes(
    chunks: list[TextChunk],
    queries: list[str],
    top_k: int = 30,
    per_query_k: int = 6,
) -> tuple[list[int], list[dict[str, Any]]]:
    selected, decisions = retrieve_chunks(chunks, queries, top_k=top_k, per_query_k=per_query_k)
    index_by_identity = {
        (chunk.title, chunk.text, tuple(chunk.page_numbers)): index for index, chunk in enumerate(chunks)
    }
    indexes = [
        index_by_identity[(chunk.title, chunk.text, tuple(chunk.page_numbers))]
        for chunk in selected
    ]
    return indexes, decisions


def load_chunks(path: str | Path) -> list[TextChunk]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        TextChunk(
            pdf_name=item.get("pdf_name", ""),
            page_numbers=item.get("page_numbers", []),
            title=item.get("title", ""),
            text=item.get("text", ""),
        )
        for item in payload
    ]


def write_retrieval_outputs(
    chunks: list[TextChunk],
    decisions: list[dict[str, Any]],
    chunks_output: str | Path,
    decisions_output: str | Path,
    queries: list[str],
) -> None:
    Path(chunks_output).parent.mkdir(parents=True, exist_ok=True)
    Path(chunks_output).write_text(
        json.dumps([asdict(chunk) for chunk in chunks], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    Path(decisions_output).parent.mkdir(parents=True, exist_ok=True)
    Path(decisions_output).write_text(
        json.dumps({"queries": queries, "decisions": decisions}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("chunks_json")
    parser.add_argument("--top-k", type=int, default=30)
    parser.add_argument("--per-query-k", type=int, default=6)
    parser.add_argument("--output", default=None)
    parser.add_argument("--decisions-output", default=None)
    add_profile_arguments(parser)
    args = parser.parse_args()
    profile = profile_from_args(args)
    chunks = load_chunks(args.chunks_json)
    queries = build_profile_queries(profile)
    selected, decisions = retrieve_chunks(chunks, queries, args.top_k, args.per_query_k)
    stem = Path(args.chunks_json).stem
    output = args.output or str(ensure_dir(DIAGNOSTICS_DIR) / f"{stem}_retrieved_chunks.json")
    decisions_output = args.decisions_output or str(
        ensure_dir(DIAGNOSTICS_DIR) / f"{stem}_retrieval_decisions.json"
    )
    write_retrieval_outputs(selected, decisions, output, decisions_output, queries)
    print(
        json.dumps(
            {
                "source_chunks": len(chunks),
                "retrieved_chunks": len(selected),
                "queries": len(queries),
                "output": output,
                "decisions_output": decisions_output,
            },
            ensure_ascii=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
