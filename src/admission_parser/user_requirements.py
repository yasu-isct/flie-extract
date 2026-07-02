from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from .profile_input import ApplicantProfileV2, add_profile_arguments, profile_from_args
from .reporter import build_report
from .utils import FINAL_JSON_DIR, FINAL_REPORTS_DIR, ensure_dir, write_json


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\n", " ").split()).strip()


def _contains_any(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(keyword and keyword.lower() in lowered for keyword in keywords)


def _blob(item: dict[str, Any]) -> str:
    return " ".join(_clean(value) for key, value in item.items() if key != "source_pages")


def _matches_profile(item: dict[str, Any], profile: ApplicantProfileV2) -> bool:
    text = _blob(item)
    targets = profile.targets
    if targets and _contains_any(text, targets):
        return True
    if profile.english_test:
        english = profile.english_test.lower()
        if english in {"toefl", "toeic", "ielts"} and english in text.lower():
            return True
    if profile.background:
        background_terms = {
            "cn_undergrad": ["外国", "海外", "中国", "外国籍", "国外"],
            "jp_undergrad": ["日本国内", "本学", "高等専門学校"],
            "overseas_undergrad": ["外国", "海外", "国外", "外国籍"],
        }.get(profile.background, [])
        if _contains_any(text, background_terms):
            return True
    return not any(marker in text for marker in ["学院", "系", "専攻", "コース"])


def _date_key(item: dict[str, Any]) -> str:
    return _clean(item.get("end_date") or item.get("start_date") or item.get("date"))


def _sort_by_date(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: _date_key(item) or "9999-99-99")


def _dedupe(items: list[dict[str, Any]], fields: tuple[str, ...]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        key = "|".join(_clean(item.get(field)).lower() for field in fields)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _doc_label(item: dict[str, Any]) -> str:
    name = _clean(item.get("name"))
    zh = _clean(item.get("name_zh"))
    if zh and zh != name:
        return f"{name}（{zh}）"
    return name


def build_user_requirements(data: dict[str, Any], profile: ApplicantProfileV2) -> dict[str, Any]:
    periods = _sort_by_date(_dedupe(data.get("application_periods", []), ("period_type", "end_date", "deadline_rule")))
    methods = _dedupe(
        [item for item in data.get("submission_methods", []) if _matches_profile(item, profile)],
        ("mode", "destination"),
    )
    docs = _dedupe(
        [item for item in data.get("required_documents", []) if _matches_profile(item, profile)],
        ("name", "conditions"),
    )
    exams = _sort_by_date(
        _dedupe(
            [item for item in data.get("exam_schedules", []) if _matches_profile(item, profile)],
            ("exam_type", "date", "time", "place"),
        )
    )
    fees = _dedupe([item for item in data.get("fees", []) if _matches_profile(item, profile)], ("amount_yen", "payment_method"))
    english = _dedupe(
        [
        item
        for item in data.get("english_requirements", [])
        if not profile.english_test or profile.english_test.lower() in _blob(item).lower()
        ],
        ("test_type", "minimum_score", "institution_code"),
    )

    required_docs = [item for item in docs if not _clean(item.get("conditions"))]
    conditional_docs = [item for item in docs if _clean(item.get("conditions"))]

    action_items: list[dict[str, str]] = []
    for period in periods[:3]:
        end = _clean(period.get("end_date"))
        rule = _clean(period.get("deadline_rule"))
        if end:
            action_items.append(
                {
                    "type": "deadline",
                    "title": _clean(period.get("period_type")) or "締切",
                    "due_date": end,
                    "message": f"{end} までに対応。締切条件: {rule or '不明'}",
                }
            )
    for doc in required_docs[:10]:
        action_items.append(
            {
                "type": "document",
                "title": _doc_label(doc),
                "due_date": "",
                "message": "提出要否と様式を確認して準備する。",
            }
        )
    for item in english[:3]:
        action_items.append(
            {
                "type": "english",
                "title": _clean(item.get("test_type")) or profile.english_test.upper(),
                "due_date": "",
                "message": "スコア提出方法、直送要否、機関コード、提出期限を確認する。",
            }
        )

    missing_confirmations = []
    if not periods:
        missing_confirmations.append("出願期間が未確定です。")
    if not docs:
        missing_confirmations.append("提出書類が未確定です。")
    if profile.english_test and not english:
        missing_confirmations.append(f"{profile.english_test.upper()} の要件が未確定です。")
    if not fees:
        missing_confirmations.append("検定料・支払方法が未確定です。")

    return {
        "generated_on": date.today().isoformat(),
        "profile": profile.model_dump(),
        "summary": {
            "deadline_count": len(periods),
            "required_document_count": len(required_docs),
            "conditional_document_count": len(conditional_docs),
            "english_requirement_count": len(english),
            "fee_count": len(fees),
            "exam_schedule_count": len(exams),
        },
        "critical_deadlines": periods[:8],
        "submission_methods": methods[:5],
        "required_documents": required_docs,
        "conditional_documents": conditional_docs,
        "english_requirements": english,
        "fees": fees,
        "exam_schedules": exams[:10],
        "action_items": action_items,
        "missing_confirmations": missing_confirmations,
    }


def enrich_json_with_requirements(
    json_path: str | Path,
    profile: ApplicantProfileV2,
    output: str | Path | None = None,
    report_output: str | Path | None = None,
) -> dict[str, Any]:
    source = Path(json_path)
    data = json.loads(source.read_text(encoding="utf-8"))
    data["_user_requirements"] = build_user_requirements(data, profile)
    output_path = Path(output) if output else ensure_dir(FINAL_JSON_DIR) / f"{source.stem}_requirements.json"
    write_json(output_path, data)
    if report_output:
        Path(report_output).parent.mkdir(parents=True, exist_ok=True)
        Path(report_output).write_text(build_report(data, profile.to_report_profile()), encoding="utf-8")
    return data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("json_path")
    parser.add_argument("--output", default=None)
    parser.add_argument("--report-output", default=None)
    add_profile_arguments(parser)
    args = parser.parse_args()
    profile = profile_from_args(args)
    output = args.output or str(ensure_dir(FINAL_JSON_DIR) / f"{Path(args.json_path).stem}_requirements.json")
    report_output = args.report_output or str(
        ensure_dir(FINAL_REPORTS_DIR) / f"{Path(output).stem}_report.md"
    )
    payload = enrich_json_with_requirements(
        args.json_path,
        profile=profile,
        output=output,
        report_output=report_output,
    )
    print(
        json.dumps(
            {
                "output": output,
                "report_output": report_output,
                "action_items": len(payload.get("_user_requirements", {}).get("action_items", [])),
                "missing_confirmations": len(
                    payload.get("_user_requirements", {}).get("missing_confirmations", [])
                ),
            },
            ensure_ascii=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
