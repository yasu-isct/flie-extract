from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

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
    backend: str = "ngram"


class EmbeddingModel(Protocol):
    def encode(self, texts: list[str], normalize_embeddings: bool = True, show_progress_bar: bool = False):
        ...


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


def dense_cosine(left, right) -> float:
    return float(sum(float(a) * float(b) for a, b in zip(left, right)))


def chunk_text(chunk: TextChunk) -> str:
    return f"{chunk.title}\n{chunk.text}"


def load_embedding_model(model_path: str | Path | None = None) -> EmbeddingModel:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "sentence-transformers is required for local embedding retrieval. "
            "Install it with `.\\.venv\\Scripts\\python.exe -m pip install sentence-transformers`."
        ) from exc

    path = str(model_path or os.getenv("LOCAL_EMBEDDING_MODEL_PATH", "models/bge-m3"))
    if not Path(path).exists():
        raise FileNotFoundError(
            f"Local embedding model path does not exist: {path}. "
            "Download BAAI/bge-m3 into models/bge-m3 or set LOCAL_EMBEDDING_MODEL_PATH."
        )
    return SentenceTransformer(path)


def _embedding_cache_key(chunks: list[TextChunk], model_path: str | Path | None) -> str:
    digest = hashlib.sha256()
    digest.update(str(model_path or os.getenv("LOCAL_EMBEDDING_MODEL_PATH", "models/bge-m3")).encode("utf-8"))
    for chunk in chunks:
        digest.update(chunk.pdf_name.encode("utf-8"))
        digest.update(str(chunk.page_numbers).encode("utf-8"))
        digest.update(chunk.title.encode("utf-8"))
        digest.update(chunk.text.encode("utf-8"))
    return digest.hexdigest()[:24]


def _load_or_encode_chunk_embeddings(
    chunks: list[TextChunk],
    model: EmbeddingModel,
    model_path: str | Path | None = None,
    cache_dir: str | Path | None = None,
):
    if not cache_dir:
        return model.encode(
            [chunk_text(chunk) for chunk in chunks],
            normalize_embeddings=True,
            show_progress_bar=False,
        )

    import numpy as np

    cache_dir = ensure_dir(cache_dir)
    cache_path = Path(cache_dir) / f"{_embedding_cache_key(chunks, model_path)}.npy"
    meta_path = Path(cache_dir) / f"{cache_path.stem}.json"
    if cache_path.exists():
        return np.load(cache_path)

    embeddings = model.encode(
        [chunk_text(chunk) for chunk in chunks],
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    np.save(cache_path, embeddings)
    meta_path.write_text(
        json.dumps(
            {
                "model_path": str(model_path or os.getenv("LOCAL_EMBEDDING_MODEL_PATH", "models/bge-m3")),
                "chunks": len(chunks),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return embeddings


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
    backend: str = "ngram",
    embedding_model_path: str | Path | None = None,
    embedding_model: EmbeddingModel | None = None,
    embedding_cache_dir: str | Path | None = None,
) -> tuple[list[TextChunk], list[dict[str, Any]]]:
    if backend == "local-embedding":
        return retrieve_chunks_by_embedding(
            chunks,
            queries,
            top_k=top_k,
            per_query_k=per_query_k,
            model_path=embedding_model_path,
            model=embedding_model,
            cache_dir=embedding_cache_dir,
        )
    if backend != "ngram":
        raise ValueError(f"Unsupported retrieval backend: {backend}")
    return retrieve_chunks_by_ngram(chunks, queries, top_k=top_k, per_query_k=per_query_k)


def retrieve_chunks_by_ngram(
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
                backend="ngram",
            )
        )
        for index in selected_indexes
    ]
    return [chunks[index] for index in selected_indexes], decisions


def retrieve_chunks_by_embedding(
    chunks: list[TextChunk],
    queries: list[str],
    top_k: int = 30,
    per_query_k: int = 6,
    model_path: str | Path | None = None,
    model: EmbeddingModel | None = None,
    cache_dir: str | Path | None = None,
) -> tuple[list[TextChunk], list[dict[str, Any]]]:
    if not chunks or not queries:
        return [], []

    model = model or load_embedding_model(model_path)
    chunk_embeddings = _load_or_encode_chunk_embeddings(
        chunks,
        model,
        model_path=model_path,
        cache_dir=cache_dir,
    )
    query_embeddings = model.encode(
        queries,
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    scores: dict[int, float] = {}
    matched_queries: dict[int, list[str]] = {}
    for query, query_embedding in zip(queries, query_embeddings):
        ranked = sorted(
            (
                (index, dense_cosine(query_embedding, chunk_embedding))
                for index, chunk_embedding in enumerate(chunk_embeddings)
            ),
            key=lambda item: item[1],
            reverse=True,
        )[:per_query_k]
        for index, score in ranked:
            scores[index] = max(scores.get(index, -1.0), score)
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
                backend="local-embedding",
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
    backend: str = "ngram",
    embedding_model_path: str | Path | None = None,
    embedding_cache_dir: str | Path | None = None,
) -> tuple[list[int], list[dict[str, Any]]]:
    selected, decisions = retrieve_chunks(
        chunks,
        queries,
        top_k=top_k,
        per_query_k=per_query_k,
        backend=backend,
        embedding_model_path=embedding_model_path,
        embedding_cache_dir=embedding_cache_dir,
    )
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
    parser.add_argument("--backend", choices=["ngram", "local-embedding"], default="ngram")
    parser.add_argument("--embedding-model-path", default=None)
    parser.add_argument("--embedding-cache-dir", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--decisions-output", default=None)
    add_profile_arguments(parser)
    args = parser.parse_args()
    profile = profile_from_args(args)
    chunks = load_chunks(args.chunks_json)
    queries = build_profile_queries(profile)
    selected, decisions = retrieve_chunks(
        chunks,
        queries,
        args.top_k,
        args.per_query_k,
        backend=args.backend,
        embedding_model_path=args.embedding_model_path,
        embedding_cache_dir=args.embedding_cache_dir,
    )
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
                "backend": args.backend,
                "output": output,
                "decisions_output": decisions_output,
            },
            ensure_ascii=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
