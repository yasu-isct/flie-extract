from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Iterable, Type

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

from .chunker import TextChunk
from .schemas import (
    AdmissionInfo,
    DocumentExtraction,
    EnglishExtraction,
    ExamExtraction,
    FeeExtraction,
    MethodExtraction,
    PeriodExtraction,
)

SYSTEM_PROMPT = """
你是日本大学院募集要項 PDF 的结构化抽取专家。
只抽取本文明确写出的信息，禁止猜测。
日期在年份明确时必须规范化为 YYYY-MM-DD；令和、平成等元号要尽量转换为西历。
必须严格区分「必着」和「消印有効」。
Markdown 表格与正文同等重要。
没有出现的信息使用空字符串、null、空列表或不明 enum。
所有 warnings、structured_warnings.message、notes、global_submission_rules 等说明性文本必须使用中文或原文日文，绝对不要输出英文回退句。
如果当前 focus 指定的信息没有在文本中出现，返回空列表即可；不要写类似 "No ... found" 的 warning。
只有在文本存在矛盾、歧义或需要人工核验时才输出 warning，并且 warning 必须是中文。
日文名称对应的中文展示字段（如 name_zh / graduate_school_zh）请尽量补充。
""".strip()

USER_TEMPLATE = """
PDF: {pdf_name}
Pages: {pages}
Section title: {title}
Extraction focus: {focus}

本文:
{text}
""".strip()

GROUP_USER_TEMPLATE = """
PDF: {pdf_name}
Pages: {pages}
Section title: {title}
Extraction focus: {focus}

The following text contains multiple selected chunks from the same information category.
Deduplicate repeated facts across chunks. Extract only information that is explicitly stated.

{text}
""".strip()

EXTRACTION_PROMPT_VERSION = "extraction_v1"

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

CATEGORY_RESPONSE_MODELS: dict[str, Type[BaseModel]] = {
    "periods": PeriodExtraction,
    "methods": MethodExtraction,
    "documents": DocumentExtraction,
    "exams": ExamExtraction,
    "fees": FeeExtraction,
    "english": EnglishExtraction,
    "general": AdmissionInfo,
}


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


def _schema_hash(response_model: Type[BaseModel]) -> str:
    payload = json.dumps(response_model.model_json_schema(), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _cache_key(
    chunk: TextChunk,
    response_model: Type[BaseModel],
    selected_model: str,
    focus: str,
    prompt_template: str,
) -> str:
    payload = {
        "prompt_version": EXTRACTION_PROMPT_VERSION,
        "system_prompt": SYSTEM_PROMPT,
        "prompt_template": prompt_template,
        "model": selected_model,
        "response_model": response_model.__name__,
        "schema_hash": _schema_hash(response_model),
        "focus": focus or "Extract clearly stated admission information only.",
        "chunk": asdict(chunk),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _cache_path(cache_dir: str | Path | None, key: str) -> Path | None:
    if not cache_dir:
        return None
    return Path(cache_dir) / f"{key}.json"


def _load_cached_response(
    cache_dir: str | Path | None,
    key: str,
    response_model: Type[BaseModel],
) -> BaseModel | None:
    path = _cache_path(cache_dir, key)
    if not path or not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return response_model.model_validate(payload["result"])


def _write_cached_response(
    cache_dir: str | Path | None,
    key: str,
    result: BaseModel,
    response_model: Type[BaseModel],
    selected_model: str,
    focus: str,
) -> None:
    path = _cache_path(cache_dir, key)
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "manifest": {
            "prompt_version": EXTRACTION_PROMPT_VERSION,
            "model": selected_model,
            "response_model": response_model.__name__,
            "schema_hash": _schema_hash(response_model),
            "focus": focus or "Extract clearly stated admission information only.",
        },
        "result": result.model_dump(mode="json"),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _create_response(
    chunk: TextChunk,
    response_model: Type[BaseModel],
    model: str | None = None,
    focus: str = "",
    cache_dir: str | Path | None = None,
    cache_stats: dict[str, int] | None = None,
) -> BaseModel:
    selected_model, use_pro_options = _model_for_chunk(chunk, model=model)
    key = _cache_key(chunk, response_model, selected_model, focus, USER_TEMPLATE)
    cached = _load_cached_response(cache_dir, key, response_model)
    if cached is not None:
        if cache_stats is not None:
            cache_stats["hits"] = cache_stats.get("hits", 0) + 1
        return cached
    if cache_stats is not None and cache_dir:
        cache_stats["misses"] = cache_stats.get("misses", 0) + 1
    client = _client()
    kwargs = {
        "model": selected_model,
        "response_model": response_model,
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
        result = client.chat.completions.create(**kwargs)
    except Exception as exc:
        error_text = repr(exc) + "\n" + str(exc)
        if use_pro_options and "Thinking mode" in error_text and "tool_choice" in error_text:
            kwargs.pop("extra_body", None)
            kwargs.pop("reasoning_effort", None)
            kwargs["max_retries"] = 2
            result = client.chat.completions.create(**kwargs)
        else:
            raise
    _write_cached_response(cache_dir, key, result, response_model, selected_model, focus)
    return result


def _focused_to_admission_info(result: BaseModel) -> AdmissionInfo:
    if isinstance(result, AdmissionInfo):
        return result
    payload = result.model_dump()
    return AdmissionInfo(
        application_periods=payload.get("application_periods", []),
        submission_methods=payload.get("submission_methods", []),
        required_documents=payload.get("required_documents", []),
        exam_schedules=payload.get("exam_schedules", []),
        fees=payload.get("fees", []),
        english_requirements=payload.get("english_requirements", []),
        global_submission_rules=payload.get("global_submission_rules", []),
        warnings=payload.get("warnings", []),
        structured_warnings=payload.get("structured_warnings", []),
    )


def parse_chunk(chunk: TextChunk, model: str | None = None, focus: str = "") -> AdmissionInfo:
    result = _create_response(chunk, AdmissionInfo, model=model, focus=focus)
    return _focused_to_admission_info(result)


def parse_chunk_by_category(
    chunk: TextChunk,
    category: str,
    model: str | None = None,
    focus: str = "",
) -> AdmissionInfo:
    response_model = CATEGORY_RESPONSE_MODELS.get(category, AdmissionInfo)
    result = _create_response(chunk, response_model, model=model, focus=focus)
    return _focused_to_admission_info(result)


def combine_chunks_for_category(
    chunks: Iterable[TextChunk],
    category: str,
    max_chars: int = 18000,
) -> list[TextChunk]:
    batches: list[TextChunk] = []
    current_parts: list[str] = []
    current_pages: set[int] = set()
    pdf_name = ""

    def flush() -> None:
        if not current_parts:
            return
        batches.append(
            TextChunk(
                pdf_name=pdf_name,
                page_numbers=sorted(current_pages),
                title=f"category:{category}",
                text="\n\n".join(current_parts).strip(),
            )
        )

    for index, chunk in enumerate(chunks, start=1):
        pdf_name = pdf_name or chunk.pdf_name
        part = (
            f"### Chunk {index}\n"
            f"Pages: {chunk.page_numbers}\n"
            f"Title: {chunk.title}\n\n"
            f"{chunk.text.strip()}"
        )
        projected_size = sum(len(item) + 2 for item in current_parts) + len(part)
        if current_parts and projected_size > max_chars:
            flush()
            current_parts = []
            current_pages = set()
        current_parts.append(part)
        current_pages.update(chunk.page_numbers)
    flush()
    return batches


def _create_group_response(
    chunk: TextChunk,
    response_model: Type[BaseModel],
    model: str | None = None,
    focus: str = "",
    cache_dir: str | Path | None = None,
    cache_stats: dict[str, int] | None = None,
) -> BaseModel:
    selected_model, use_pro_options = _model_for_chunk(chunk, model=model)
    key = _cache_key(chunk, response_model, selected_model, focus, GROUP_USER_TEMPLATE)
    cached = _load_cached_response(cache_dir, key, response_model)
    if cached is not None:
        if cache_stats is not None:
            cache_stats["hits"] = cache_stats.get("hits", 0) + 1
        return cached
    if cache_stats is not None and cache_dir:
        cache_stats["misses"] = cache_stats.get("misses", 0) + 1
    client = _client()
    kwargs = {
        "model": selected_model,
        "response_model": response_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": GROUP_USER_TEMPLATE.format(
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
        result = client.chat.completions.create(**kwargs)
    except Exception as exc:
        error_text = repr(exc) + "\n" + str(exc)
        if use_pro_options and "Thinking mode" in error_text and "tool_choice" in error_text:
            kwargs.pop("extra_body", None)
            kwargs.pop("reasoning_effort", None)
            kwargs["max_retries"] = 2
            result = client.chat.completions.create(**kwargs)
        else:
            raise
    _write_cached_response(cache_dir, key, result, response_model, selected_model, focus)
    return result


def parse_category_batch(
    chunks: Iterable[TextChunk],
    category: str,
    model: str | None = None,
    focus: str = "",
    max_chars: int = 18000,
    cache_dir: str | Path | None = None,
    cache_stats: dict[str, int] | None = None,
) -> list[AdmissionInfo]:
    response_model = CATEGORY_RESPONSE_MODELS.get(category, AdmissionInfo)
    partials: list[AdmissionInfo] = []
    for batch in combine_chunks_for_category(chunks, category=category, max_chars=max_chars):
        result = _create_group_response(
            batch,
            response_model,
            model=model,
            focus=focus,
            cache_dir=cache_dir,
            cache_stats=cache_stats,
        )
        partials.append(_focused_to_admission_info(result))
    return partials


def parse_chunks(chunks: Iterable[TextChunk], model: str | None = None) -> list[AdmissionInfo]:
    return [parse_chunk(chunk, model=model) for chunk in chunks]


def chunk_payload(chunk: TextChunk) -> dict:
    return asdict(chunk)
