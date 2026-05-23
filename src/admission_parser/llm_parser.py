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
Extraction focus: {focus}

本文:
{text}
""".strip()

COMPLEX_KEYWORDS = (
    "提出書類",
    "出願資格",
    "検定料",
    "英語",
    "TOEFL",
    "TOEIC",
    "IELTS",
    "必着",
    "消印有効",
    "該当者",
    "外国人",
    "条件",
    "免除",
)


def _client():
    load_dotenv()
    try:
        import instructor
    except ImportError as exc:
        raise RuntimeError("instructor is not installed. Run `pip install -e .[dev]`.") from exc
    base_url = os.getenv("OPENAI_BASE_URL")
    client = OpenAI(base_url=base_url) if base_url else OpenAI()
    mode_name = os.getenv("INSTRUCTOR_MODE", "JSON").upper()
    mode = getattr(instructor.Mode, mode_name, instructor.Mode.JSON)
    return instructor.from_openai(client, mode=mode)


def is_complex_chunk(chunk: TextChunk) -> bool:
    threshold = int(os.getenv("LLM_PRO_COMPLEX_CHAR_THRESHOLD", "7000"))
    if len(chunk.text) >= threshold:
        return True
    haystack = f"{chunk.title}\n{chunk.text}"
    keyword_hits = sum(1 for keyword in COMPLEX_KEYWORDS if keyword in haystack)
    return len(chunk.text) >= 2500 and keyword_hits >= 3


def _model_for_chunk(chunk: TextChunk, model: str | None = None) -> tuple[str, bool]:
    load_dotenv()
    if model:
        return model, False
    default_model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    pro_model = os.getenv("OPENAI_PRO_MODEL", "deepseek-v4-pro")
    use_pro = os.getenv("LLM_USE_PRO_FOR_COMPLEX", "true").lower() in {"1", "true", "yes"}
    if use_pro and is_complex_chunk(chunk):
        return pro_model, True
    return default_model, False


def parse_chunk(chunk: TextChunk, model: str | None = None, focus: str = "") -> AdmissionInfo:
    selected_model, use_pro_options = _model_for_chunk(chunk, model=model)
    client = _client()
    kwargs = {
        "model": selected_model,
        "response_model": AdmissionInfo,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": USER_TEMPLATE.format(
                    pdf_name=chunk.pdf_name,
                    pages=chunk.page_numbers,
                    title=chunk.title,
                    focus=focus or "Extract clearly stated admission information only.",
                    text=chunk.text,
                ),
            },
        ],
        "max_retries": 2,
    }
    if use_pro_options:
        if os.getenv("OPENAI_PRO_REASONING_ENABLED", "false").lower() in {"1", "true", "yes"}:
            kwargs["reasoning_effort"] = os.getenv("OPENAI_PRO_REASONING_EFFORT", "high")
        if os.getenv("OPENAI_PRO_THINKING_ENABLED", "false").lower() in {"1", "true", "yes"}:
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
            kwargs["max_retries"] = 1
    try:
        return client.chat.completions.create(**kwargs)
    except Exception as exc:
        error_text = repr(exc) + "\n" + str(exc)
        if use_pro_options and "Thinking mode" in error_text and "tool_choice" in error_text:
            kwargs.pop("extra_body", None)
            kwargs["max_retries"] = 2
            return client.chat.completions.create(**kwargs)
        raise


def parse_chunks(chunks: Iterable[TextChunk], model: str | None = None) -> list[AdmissionInfo]:
    return [parse_chunk(chunk, model=model) for chunk in chunks]


def chunk_payload(chunk: TextChunk) -> dict:
    return asdict(chunk)
