from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LOW_VALUE_PATTERNS = [
    r"注意事項は.*確認すること",
    r"詳細は.*参照",
    r"本文参照",
    r"No admission",
    r"出願情報.*含まれていません",
    r"抽出できません",
    r"具体的な.*情報.*含まれていません",
]

PROGRAM_MARKERS = [
    "学院",
    "研究科",
    "専攻",
    "系",
    "コース",
    "情報理工",
    "工学院",
    "物質理工",
    "生命理工",
    "環境",
    "数学系",
    "数理",
    "計算",
    "情報工学",
]

BACKGROUND_RULES = {
    "cn_undergrad": {
        "label": "中国大陆全日制本科",
        "include": ["外国", "留学生", "海外", "中国", "国外", "外国籍"],
        "exclude": ["本学に在学中", "本学の者は", "日本国内の他大学"],
    },
    "jp_undergrad": {
        "label": "日本本科",
        "include": ["日本国内", "大学", "高等専門学校", "本学に在学中"],
        "exclude": ["外国政府奨学金", "中国政府", "清華大学"],
    },
    "overseas_undergrad": {
        "label": "海外本科",
        "include": ["外国", "留学生", "海外", "国外", "外国籍"],
        "exclude": ["本学に在学中", "本学の者は"],
    },
}

ENGLISH_ALIASES = {
    "toeic": ["TOEIC", "TOEIC L&R"],
    "toefl": ["TOEFL", "TOEFL iBT", "TOEFL iBT Home Edition"],
    "ielts": ["IELTS"],
}


@dataclass
class ApplicantProfile:
    targets: list[str] = field(default_factory=list)
    english_test: str = ""
    background: str = ""

    @property
    def background_label(self) -> str:
        return BACKGROUND_RULES.get(self.background, {}).get("label", self.background or "未指定")


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\n", " ").split()).strip()


def _blob(item: dict[str, Any]) -> str:
    return " ".join(_clean(value) for key, value in item.items() if key != "source_pages")


def _is_low_value(text: Any) -> bool:
    text = _clean(text)
    if not text:
        return True
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in LOW_VALUE_PATTERNS)


def _shorten(text: Any, limit: int = 160) -> str:
    text = _clean(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."


def _norm_key(text: Any) -> str:
    return re.sub(r"[\s　・、。，．（）()「」『』:：/／\-]+", "", _clean(text)).lower()


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword and keyword.lower() in text.lower() for keyword in keywords)


def _has_program_marker(text: str) -> bool:
    return _contains_any(text, PROGRAM_MARKERS)


def _matches_target(item: dict[str, Any], profile: ApplicantProfile) -> bool:
    if not profile.targets:
        return True
    text = _blob(item)
    if _contains_any(text, profile.targets):
        return True
    return not _has_program_marker(text)


def _matches_english(item: dict[str, Any], profile: ApplicantProfile) -> bool:
    if not profile.english_test:
        return True
    text = _blob(item)
    aliases = ENGLISH_ALIASES.get(profile.english_test.lower(), [profile.english_test])
    if _contains_any(text, aliases):
        return True
    if not _contains_any(text, sum(ENGLISH_ALIASES.values(), [])):
        return True
    return False


def _matches_background(item: dict[str, Any], profile: ApplicantProfile) -> bool:
    if not profile.background:
        return True
    text = _blob(item)
    rules = BACKGROUND_RULES.get(profile.background, {})
    if _contains_any(text, rules.get("exclude", [])):
        return False
    include = rules.get("include", [])
    if not include:
        return True
    condition = _clean(item.get("conditions"))
    if not condition:
        return True
    return _contains_any(text, include)


def _profile_filter(items: list[dict[str, Any]], profile: ApplicantProfile) -> list[dict[str, Any]]:
    return [
        item
        for item in items
        if _matches_target(item, profile)
        and _matches_background(item, profile)
        and _matches_english(item, profile)
    ]


def _date_range(item: dict[str, Any]) -> str:
    start = _clean(item.get("start_date"))
    end = _clean(item.get("end_date"))
    time = _clean(item.get("time"))
    rule = _clean(item.get("deadline_rule"))
    if start and end:
        base = f"{start} - {end}"
    elif end:
        base = f"截止 {end}"
    elif start:
        base = f"开始 {start}"
    else:
        base = "日期待确认"
    extras = []
    if time:
        extras.append(time)
    if rule and rule != "不明":
        extras.append(rule)
    return base + (f" ({' / '.join(extras)})" if extras else "")


def _dedupe(items: list[dict[str, Any]], fields: tuple[str, ...]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        key = "|".join(_norm_key(item.get(field)) for field in fields)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _best_item(items: list[dict[str, Any]]) -> dict[str, Any]:
    def score(item: dict[str, Any]) -> int:
        useful = 0
        for key, value in item.items():
            if key == "source_pages":
                continue
            text = _clean(value)
            if text and not _is_low_value(text):
                useful += min(len(text), 120)
        return useful

    return max(items, key=score)


def _group_documents(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for doc in docs:
        name = _clean(doc.get("name"))
        if not name or "不完全" in name:
            continue
        groups.setdefault(_norm_key(name), []).append(doc)

    merged = []
    for group in groups.values():
        item = dict(_best_item(group))
        conditions = []
        notes = []
        for doc in group:
            condition = _clean(doc.get("conditions"))
            note = _clean(doc.get("notes"))
            if condition:
                conditions.append(condition)
            if not _is_low_value(note):
                notes.append(note)
        if conditions:
            item["conditions"] = " / ".join(dict.fromkeys(conditions))
        if notes:
            item["notes"] = " / ".join(dict.fromkeys(notes))
        merged.append(item)
    return merged


def _group_methods(methods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for method in methods:
        mode = _clean(method.get("mode")) or "不明"
        if mode == "不明" and not method.get("details") and not method.get("destination"):
            continue
        groups.setdefault(mode, []).append(method)

    result = []
    for mode, group in groups.items():
        details = []
        destinations = []
        for item in group:
            if item.get("details"):
                details.append(_shorten(item.get("details"), 120))
            if item.get("destination"):
                destinations.append(_shorten(item.get("destination"), 120))
        result.append(
            {
                "mode": mode,
                "details": " / ".join(dict.fromkeys(details[:3])),
                "destination": " / ".join(dict.fromkeys(destinations[:3])),
            }
        )
    return result


def _group_fees(fees: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for fee in fees:
        key = str(fee.get("amount_yen") or "unknown")
        groups.setdefault(key, []).append(fee)
    return [_best_item(group) for group in groups.values()]


def _filter_periods(periods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dated_types = {_norm_key(item.get("period_type")) for item in periods if item.get("start_date") or item.get("end_date")}
    result = []
    for item in periods:
        period_type = _norm_key(item.get("period_type"))
        if not item.get("start_date") and not item.get("end_date") and period_type in dated_types:
            continue
        if _is_low_value(item.get("period_type")):
            continue
        result.append(item)
    return result


def _line_parts(*parts: str) -> str:
    return "；".join(part for part in (_clean(part) for part in parts) if part)


def _document_line(doc: dict[str, Any]) -> str:
    name = _clean(doc.get("name"))
    name_zh = _clean(doc.get("name_zh"))
    copies = _clean(doc.get("copies"))
    condition = _clean(doc.get("conditions"))
    has_form = doc.get("has_form")
    notes = "" if _is_low_value(doc.get("notes")) else _shorten(doc.get("notes"))

    label = name
    if name_zh and name_zh != name:
        label += f"（{name_zh}）"
    details = []
    if copies:
        details.append(f"份数: {copies}")
    if has_form is True:
        details.append("有指定格式")
    elif has_form is False:
        details.append("无指定格式")
    if condition:
        details.append(f"条件: {_shorten(condition, 120)}")
    if notes:
        details.append(notes)
    return f"- {label}" + (f": {'；'.join(details)}" if details else "")


def _profile_lines(profile: ApplicantProfile) -> list[str]:
    targets = "、".join(profile.targets) if profile.targets else "未指定"
    english = profile.english_test.upper() if profile.english_test else "未指定"
    return [
        "## 申请者画像",
        "",
        f"- 目标学院/系/专攻关键词: {targets}",
        f"- 英语考试类型: {english}",
        f"- 学历/身份背景: {profile.background_label}",
        "",
    ]


def build_report(data: dict[str, Any], profile: ApplicantProfile | None = None) -> str:
    profile = profile or ApplicantProfile()
    university = data.get("university", {})
    title = _clean(university.get("university_name")) or "募集要項解析报告"
    school = _clean(university.get("graduate_school"))
    year = university.get("admission_year")

    lines = [
        f"# {title} 个人申请摘要",
        "",
        "## 基本信息",
        "",
        f"- 大学: {title}",
        f"- 研究科/学院: {school or '待确认'}",
        f"- 入试年度: {year or '待确认'}",
        f"- 来源 PDF: {_clean(university.get('source_pdf')) or '待确认'}",
        "",
    ]
    lines += _profile_lines(profile)

    periods = _profile_filter(data.get("application_periods", []), profile)
    periods = _dedupe(periods, ("period_type", "start_date", "end_date", "deadline_rule"))
    useful_periods = _filter_periods(periods)
    lines += ["## 关键时间", ""]
    for item in useful_periods:
        note = "" if _is_low_value(item.get("notes")) else _shorten(item.get("notes"), 120)
        line = f"- {_clean(item.get('period_type'))}: {_date_range(item)}"
        if note:
            line += f"；{note}"
        lines.append(line)
    if not useful_periods:
        lines.append("- 未抽取到与该画像明确匹配的时间信息。")
    lines.append("")

    fees = _group_fees(_profile_filter(data.get("fees", []), profile))
    lines += ["## 费用", ""]
    useful_fees = [fee for fee in fees if fee.get("amount_yen") or fee.get("payment_method") or fee.get("notes")]
    for fee in useful_fees:
        amount = f"{fee.get('amount_yen'):,} 日元" if fee.get("amount_yen") else "金额待确认"
        detail = _line_parts(
            f"支付方式: {_clean(fee.get('payment_method'))}" if fee.get("payment_method") else "",
            f"支付期间: {_clean(fee.get('payment_period'))}" if fee.get("payment_period") else "",
            "" if _is_low_value(fee.get("notes")) else _shorten(fee.get("notes"), 140),
        )
        lines.append(f"- {amount}" + (f": {detail}" if detail else ""))
    if not useful_fees:
        lines.append("- 未抽取到费用信息。")
    lines.append("")

    methods = _group_methods(_profile_filter(data.get("submission_methods", []), profile))
    lines += ["## 出愿/提交方式", ""]
    for method in methods:
        line = f"- {_clean(method.get('mode')) or '方式待确认'}"
        detail = _line_parts(
            _shorten(method.get("details"), 160),
            f"提交/邮寄至: {_shorten(method.get('destination'), 120)}" if method.get("destination") else "",
        )
        if detail:
            line += f": {detail}"
        lines.append(line)
    if not methods:
        lines.append("- 未抽取到提交方式。")
    lines.append("")

    docs = _group_documents(_profile_filter(data.get("required_documents", []), profile))
    required_docs = [doc for doc in docs if doc.get("name") and not doc.get("conditions")]
    conditional_docs = [doc for doc in docs if doc.get("name") and doc.get("conditions")]
    lines += ["## 提交材料清单", "", "### 通用材料", ""]
    lines += [_document_line(doc) for doc in required_docs] or ["- 未抽取到通用材料。"]
    lines += ["", "### 与你的背景相关的条件材料", ""]
    lines += [_document_line(doc) for doc in conditional_docs] or ["- 当前画像下未抽取到条件材料。"]
    lines.append("")

    exams = _profile_filter(data.get("exam_schedules", []), profile)
    exams = _dedupe(exams, ("exam_type", "date", "time", "notes"))
    lines += ["## 考试与发表日程", ""]
    useful_exams = [exam for exam in exams if exam.get("exam_type") or exam.get("date") or exam.get("notes")]
    for exam in useful_exams:
        when = _date_range({"start_date": exam.get("date"), "end_date": exam.get("date"), "time": exam.get("time")})
        detail = _line_parts(
            f"地点: {_clean(exam.get('place'))}" if exam.get("place") else "",
            "" if _is_low_value(exam.get("notes")) else _shorten(exam.get("notes"), 140),
        )
        lines.append(f"- {_clean(exam.get('exam_type')) or '事项'}: {when}" + (f"；{detail}" if detail else ""))
    if not useful_exams:
        lines.append("- 未抽取到与该画像明确匹配的考试日程。")
    lines.append("")

    english = _profile_filter(data.get("english_requirements", []), profile)
    english = _dedupe(english, ("test_type", "minimum_score", "notes"))
    lines += ["## 英语成绩要求", ""]
    useful_english = [item for item in english if item.get("test_type") or item.get("notes")]
    for item in useful_english:
        detail = _line_parts(
            f"接受类型: {'、'.join(item.get('accepted_variants', []))}" if item.get("accepted_variants") else "",
            f"不接受类型: {'、'.join(item.get('rejected_variants', []))}" if item.get("rejected_variants") else "",
            f"最低分: {_clean(item.get('minimum_score'))}" if item.get("minimum_score") else "",
            "需直送" if item.get("direct_delivery_required") is True else "",
            f"机构代码: {_clean(item.get('institution_code'))}" if item.get("institution_code") else "",
            f"适用对象: {_shorten(item.get('applicable_to'), 100)}" if item.get("applicable_to") else "",
            f"例外: {' / '.join(item.get('exceptions', []))}" if item.get("exceptions") else "",
            f"条件: {_clean(item.get('condition_logic'))}" if item.get("condition_logic") not in ("", "UNKNOWN", None) else "",
            "" if _is_low_value(item.get("notes")) else _shorten(item.get("notes"), 180),
        )
        lines.append(f"- {_clean(item.get('test_type')) or '英语要求'}" + (f": {detail}" if detail else ""))
    if not useful_english:
        lines.append("- 未抽取到与该英语考试类型明确匹配的要求。")
    lines.append("")

    warnings = [warning for warning in data.get("warnings", []) if not _is_low_value(warning)]
    lines += ["## 需要人工确认", ""]
    if warnings:
        for warning in _dedupe([{"warning": w} for w in warnings], ("warning",))[:10]:
            lines.append(f"- {_shorten(warning['warning'], 180)}")
    else:
        lines.append("- 暂无高价值警告。")
    lines.append("")

    lines += [
        "---",
        "",
        "说明: 本报告根据申请者画像从结构化 JSON 中自动筛选生成。因为 PDF 原文中部分信息未显式绑定专攻，仍建议对照原 PDF 核验关键日期、考试科目和提交材料。",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("json_path")
    parser.add_argument("--output", default=None)
    parser.add_argument("--target", action="append", default=[], help="目标学院、系、专攻关键词。可重复传入。")
    parser.add_argument("--english-test", default="", help="英语考试类型，如 toeic/toefl/ielts。")
    parser.add_argument(
        "--background",
        default="",
        choices=["", "cn_undergrad", "jp_undergrad", "overseas_undergrad"],
        help="申请者背景。",
    )
    args = parser.parse_args()
    json_path = Path(args.json_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    profile = ApplicantProfile(
        targets=args.target,
        english_test=args.english_test,
        background=args.background,
    )
    output = Path(args.output) if args.output else json_path.with_name(f"{json_path.stem}_report.md")
    output.write_text(build_report(data, profile), encoding="utf-8")
    print(str(output))


if __name__ == "__main__":
    main()
