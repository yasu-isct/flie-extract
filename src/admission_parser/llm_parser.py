from __future__ import annotations

import os
from dataclasses import asdict
from typing import Iterable

from dotenv import load_dotenv
from openai import OpenAI

from .chunker import TextChunk
from .schemas import AdmissionInfo

SYSTEM_PROMPT = """
あなたは日本の大学院募集要項PDFから出願情報を抽出する専門家です。
必ず与えられた本文に書かれている情報だけを抽出してください。推測は禁止です。
日付は可能な限り西暦 ISO 形式 YYYY-MM-DD に正規化してください。
令和・平成などの元号は西暦に変換してください。
「必着」と「消印有効」は厳密に区別してください。
表の内容も本文と同じ重要度で扱ってください。
不明な項目は空文字、null、または不明 enum を使ってください。
主要な日本語名称には、中文表示用の name_zh / graduate_school_zh も可能な範囲で付与してください。
""".strip()

USER_TEMPLATE = """
PDF: {pdf_name}
Pages: {pages}
Section title: {title}

本文:
{text}
""".strip()


def _client():
    load_dotenv()
    try:
        import instructor
    except ImportError as exc:
        raise RuntimeError("instructor is not installed. Run `pip install -e .[dev]`.") from exc
    return instructor.from_openai(OpenAI())


def parse_chunk(chunk: TextChunk, model: str | None = None) -> AdmissionInfo:
    model = model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    client = _client()
    return client.chat.completions.create(
        model=model,
        response_model=AdmissionInfo,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": USER_TEMPLATE.format(
                    pdf_name=chunk.pdf_name,
                    pages=chunk.page_numbers,
                    title=chunk.title,
                    text=chunk.text,
                ),
            },
        ],
        max_retries=2,
    )


def parse_chunks(chunks: Iterable[TextChunk], model: str | None = None) -> list[AdmissionInfo]:
    return [parse_chunk(chunk, model=model) for chunk in chunks]


def chunk_payload(chunk: TextChunk) -> dict:
    return asdict(chunk)
