from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Iterable, TypeVar

from pydantic import BaseModel

from .schemas import AdmissionInfo, ExtractionWarning, UniversityInfo

T = TypeVar("T", bound=BaseModel)


def _key(item: BaseModel) -> str:
    payload = item.model_dump(mode="json", exclude={"source_pages"})
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _norm(value: object) -> str:
    text = "" if value is None else str(value)
    return re.sub(r"[\s　、。，．・「」『』（）()\[\]【】:：/／\-]+", "", text).lower()


def _similar(left: object, right: object, threshold: float = 0.86) -> bool:
    left_norm = _norm(left)
    right_norm = _norm(right)
    if not left_norm or not right_norm:
        return False
    if left_norm == right_norm:
        return True
    if left_norm in right_norm or right_norm in left_norm:
        return True
    return SequenceMatcher(None, left_norm, right_norm).ratio() >= threshold


def _join_unique(*values: object, separator: str = " / ") -> str:
    result = []
    for value in values:
        text = "" if value is None else str(value).strip()
        if not text:
            continue
        parts = [part.strip() for part in text.split(separator) if part.strip()]
        for part in parts:
            if all(not _similar(part, existing, 0.92) for existing in result):
                result.append(part)
    return separator.join(result)


def _merge_lists(*lists: list[str]) -> list[str]:
    result: list[str] = []
    for values in lists:
        for value in values or []:
            if value and _norm(value) not in {_norm(existing) for existing in result}:
                result.append(value)
    return result


def _merge_pages(*page_lists: list[int]) -> list[int]:
    pages = sorted({page for page_list in page_lists for page in (page_list or [])})
    return pages


def _merge_condition_logic(existing: str, new: str) -> str:
    allowed = {"AND", "OR", "UNKNOWN"}
    existing = existing if existing in allowed else "UNKNOWN"
    new = new if new in allowed else "UNKNOWN"
    if existing == "UNKNOWN":
        return new
    if new == "UNKNOWN" or new == existing:
        return existing
    return existing


def _merge_model(existing: T, new: T) -> T:
    data = existing.model_dump(mode="json")
    incoming = new.model_dump(mode="json")
    for field, value in incoming.items():
        if field == "source_pages":
            data[field] = _merge_pages(data.get(field, []), value or [])
        elif field == "condition_logic":
            data[field] = _merge_condition_logic(data.get(field, "UNKNOWN"), value)
        elif isinstance(data.get(field), list) and isinstance(value, list):
            data[field] = _merge_lists(data.get(field, []), value)
        elif isinstance(data.get(field), str) and isinstance(value, str):
            data[field] = _join_unique(data.get(field, ""), value)
        elif data.get(field) in (None, "", [], {}):
            data[field] = value
    return type(existing)(**data)


def _same_period(left: BaseModel, right: BaseModel) -> bool:
    if left.start_date or left.end_date or right.start_date or right.end_date:
        return (
            (left.start_date or "") == (right.start_date or "")
            and (left.end_date or "") == (right.end_date or "")
            and left.deadline_rule == right.deadline_rule
            and _similar(left.period_type, right.period_type, 0.75)
        )
    return _similar(left.period_type, right.period_type, 0.8) and _similar(left.notes, right.notes, 0.88)


def _same_document(left: BaseModel, right: BaseModel) -> bool:
    return _similar(left.name, right.name, 0.9)


def _same_method(left: BaseModel, right: BaseModel) -> bool:
    return left.mode == right.mode and (
        _similar(left.destination, right.destination, 0.85)
        or _similar(left.details, right.details, 0.88)
    )


def _same_exam(left: BaseModel, right: BaseModel) -> bool:
    if (left.date or right.date) and left.date != right.date:
        return False
    return _similar(left.exam_type, right.exam_type, 0.82) and (
        _similar(left.time, right.time, 0.82) or _similar(left.notes, right.notes, 0.88)
    )


def _same_fee(left: BaseModel, right: BaseModel) -> bool:
    if left.amount_yen and right.amount_yen and left.amount_yen != right.amount_yen:
        return False
    if left.amount_yen or right.amount_yen:
        return _similar(left.payment_method, right.payment_method, 0.72) or _similar(left.notes, right.notes, 0.8)
    return _similar(left.payment_method, right.payment_method, 0.84) and _similar(left.notes, right.notes, 0.84)


def _same_english(left: BaseModel, right: BaseModel) -> bool:
    left_tests = [_norm(value) for value in [left.test_type, *left.accepted_variants] if value]
    right_tests = [_norm(value) for value in [right.test_type, *right.accepted_variants] if value]
    for left_test in left_tests:
        for right_test in right_tests:
            if left_test and right_test and (left_test in right_test or right_test in left_test):
                return True
            if left_test and right_test and SequenceMatcher(None, left_test, right_test).ratio() >= 0.72:
                return True
    return _similar(left.notes, right.notes, 0.88)


def _merge_list(items: Iterable[T], same_item=None) -> list[T]:
    merged: list[T] = []
    seen: set[str] = set()
    for item in items:
        key = _key(item)
        if key in seen:
            continue
        seen.add(key)
        if same_item:
            for index, existing in enumerate(merged):
                if same_item(existing, item):
                    merged[index] = _merge_model(existing, item)
                    break
            else:
                merged.append(item)
        else:
            merged.append(item)
    return merged


def _prefer_university(infos: list[AdmissionInfo]) -> UniversityInfo:
    result = UniversityInfo()
    for info in infos:
        current = info.university
        for field, value in current.model_dump().items():
            if value not in (None, "", []):
                setattr(result, field, value)
    return result


def _warning_field(message: str) -> str:
    text = message.lower()
    if "fee" in text or "検定料" in message or "費用" in message or "金额" in message:
        return "fees"
    if "exam" in text or "試験" in message or "考试" in message:
        return "exam_schedules"
    if "english" in text or "英語" in message or "TOEFL" in message or "TOEIC" in message:
        return "english_requirements"
    if "document" in text or "書類" in message or "材料" in message:
        return "required_documents"
    if "date" in text or "日付" in message or "日期" in message:
        return "application_periods"
    return "general"


def warning_to_structured(message: str) -> ExtractionWarning:
    return ExtractionWarning(field=_warning_field(message), message=message, category="legacy_warning")


def _merge_warnings(infos: list[AdmissionInfo]) -> tuple[list[str], list[ExtractionWarning]]:
    warnings = _merge_plain_warnings(warning for info in infos for warning in info.warnings)
    structured = [
        warning
        for info in infos
        for warning in info.structured_warnings
        if warning.message
    ]
    structured.extend(warning_to_structured(warning) for warning in warnings)
    structured = _merge_list(structured, lambda left, right: left.field == right.field and _similar(left.message, right.message, 0.9))
    return warnings, structured


def _merge_plain_warnings(warnings: Iterable[str]) -> list[str]:
    result: list[str] = []
    for warning in warnings:
        if not warning:
            continue
        if all(not _similar(warning, existing, 0.9) for existing in result):
            result.append(warning)
    return result


def merge_admission_infos(infos: list[AdmissionInfo]) -> AdmissionInfo:
    if not infos:
        return AdmissionInfo()
    warnings, structured_warnings = _merge_warnings(infos)
    return AdmissionInfo(
        university=_prefer_university(infos),
        application_periods=_merge_list((item for info in infos for item in info.application_periods), _same_period),
        submission_methods=_merge_list((item for info in infos for item in info.submission_methods), _same_method),
        required_documents=_merge_list((item for info in infos for item in info.required_documents), _same_document),
        exam_schedules=_merge_list((item for info in infos for item in info.exam_schedules), _same_exam),
        fees=_merge_list((item for info in infos for item in info.fees), _same_fee),
        english_requirements=_merge_list((item for info in infos for item in info.english_requirements), _same_english),
        global_submission_rules=sorted({rule for info in infos for rule in info.global_submission_rules}),
        warnings=warnings,
        structured_warnings=structured_warnings,
    )
