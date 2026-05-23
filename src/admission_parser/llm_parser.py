from __future__ import annotations

import os
from dataclasses import asdict
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
You extract structured admission information from Japanese graduate admission guideline PDFs.
Use only information explicitly present in the provided text. Do not guess.
Normalize dates to ISO format YYYY-MM-DD when the year is clear.
Convert Japanese era years such as 令和 and 平成 to Gregorian years when possible.
Strictly distinguish 必着 from 消印有効.
Treat Markdown tables as equally important as prose.
Use empty strings, null, empty lists, or unknown enum values when information is not present.
For Japanese names, add Chinese display names when the schema has a *_zh field.
""".strip()

USER_TEMPLATE = """
PDF: {pdf_name}
Pages: {pages}
Section title: {title}
Extraction focus: {focus}

Text:
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


def _create_response(
    chunk: TextChunk,
    response_model: Type[BaseModel],
    model: str | None = None,
    focus: str = "",
) -> BaseModel:
    selected_model, use_pro_options = _model_for_chunk(chunk, model=model)
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
        return client.chat.completions.create(**kwargs)
    except Exception as exc:
        error_text = repr(exc) + "\n" + str(exc)
        if use_pro_options and "Thinking mode" in error_text and "tool_choice" in error_text:
            kwargs.pop("extra_body", None)
            kwargs.pop("reasoning_effort", None)
            kwargs["max_retries"] = 2
            return client.chat.completions.create(**kwargs)
        raise


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


def parse_chunks(chunks: Iterable[TextChunk], model: str | None = None) -> list[AdmissionInfo]:
    return [parse_chunk(chunk, model=model) for chunk in chunks]


def chunk_payload(chunk: TextChunk) -> dict:
    return asdict(chunk)
