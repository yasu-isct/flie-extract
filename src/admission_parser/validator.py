from __future__ import annotations

import re
from datetime import date

from .schemas import AdmissionInfo

ERA_START = {
    "令和": 2018,
    "平成": 1988,
    "昭和": 1925,
}
ERA_DATE_RE = re.compile(r"(令和|平成|昭和)\s*([0-9元]+)\s*年\s*([0-9]{1,2})\s*月\s*([0-9]{1,2})\s*日")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def convert_era_date(text: str | None) -> str | None:
    if not text:
        return text
    match = ERA_DATE_RE.search(text)
    if not match:
        return text
    era, year_raw, month, day = match.groups()
    year = 1 if year_raw == "元" else int(year_raw)
    western_year = ERA_START[era] + year
    return f"{western_year:04d}-{int(month):02d}-{int(day):02d}"


def _parse_iso(value: str | None) -> date | None:
    if not value or not ISO_DATE_RE.match(value):
        return None
    return date.fromisoformat(value)


def normalize_dates(info: AdmissionInfo) -> AdmissionInfo:
    for period in info.application_periods:
        period.start_date = convert_era_date(period.start_date)
        period.end_date = convert_era_date(period.end_date)
    for exam in info.exam_schedules:
        exam.date = convert_era_date(exam.date)
    return info


def validate_admission_info(info: AdmissionInfo) -> list[str]:
    errors: list[str] = []
    normalize_dates(info)

    for idx, period in enumerate(info.application_periods, start=1):
        start = _parse_iso(period.start_date)
        end = _parse_iso(period.end_date)
        if start and end:
            if start > end:
                errors.append(f"application_periods[{idx}] start_date is after end_date")
            if (end - start).days > 180:
                errors.append(f"application_periods[{idx}] duration is unusually long")
        if not period.period_type:
            errors.append(f"application_periods[{idx}] period_type is empty")

    for idx, doc in enumerate(info.required_documents, start=1):
        if not doc.name:
            errors.append(f"required_documents[{idx}] name is empty")

    return errors
