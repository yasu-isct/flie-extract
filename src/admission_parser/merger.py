from __future__ import annotations

import json
from typing import Iterable, TypeVar

from pydantic import BaseModel

from .schemas import AdmissionInfo, UniversityInfo

T = TypeVar("T", bound=BaseModel)


def _key(item: BaseModel) -> str:
    payload = item.model_dump(mode="json", exclude={"source_pages"})
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _merge_list(items: Iterable[T]) -> list[T]:
    seen: set[str] = set()
    merged: list[T] = []
    for item in items:
        key = _key(item)
        if key in seen:
            continue
        seen.add(key)
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


def merge_admission_infos(infos: list[AdmissionInfo]) -> AdmissionInfo:
    if not infos:
        return AdmissionInfo()
    return AdmissionInfo(
        university=_prefer_university(infos),
        application_periods=_merge_list(item for info in infos for item in info.application_periods),
        submission_methods=_merge_list(item for info in infos for item in info.submission_methods),
        required_documents=_merge_list(item for info in infos for item in info.required_documents),
        exam_schedules=_merge_list(item for info in infos for item in info.exam_schedules),
        fees=_merge_list(item for info in infos for item in info.fees),
        english_requirements=_merge_list(item for info in infos for item in info.english_requirements),
        global_submission_rules=sorted({rule for info in infos for rule in info.global_submission_rules}),
        warnings=[warning for info in infos for warning in info.warnings],
    )
