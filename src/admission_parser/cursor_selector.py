from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .chunker import TextChunk
from .profile_input import ApplicantProfileV2

GLOBAL_SECTION_KEYWORDS = [
    "出願期間",
    "出願手続",
    "出願方法",
    "出願書類",
    "提出書類",
    "検定料",
    "入学検定料",
    "受験票",
    "合格発表",
    "出願資格",
    "必着",
    "消印有効",
    "試験日程",
]

ACTION_KEYWORDS = [
    "提出",
    "書類",
    "証明",
    "資格",
    "検定料",
    "支払",
    "郵送",
    "登録",
    "受験",
    "試験",
]

PROGRAM_MARKERS = [
    "学院",
    "系",
    "専攻",
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
    "電気電子",
    "材料",
    "応用化学",
]

ENGLISH_ALIASES = {
    "toeic": ["TOEIC", "TOEIC L&R"],
    "toefl": ["TOEFL", "TOEFL iBT", "TOEFL iBT Home Edition"],
    "ielts": ["IELTS"],
}

BACKGROUND_ALIASES = {
    "cn_undergrad": ["外国", "外国籍", "留学生", "海外", "国外", "中国", "外国の大学", "学位取得証明"],
    "jp_undergrad": ["日本国内", "本学", "高等専門学校", "在学証明"],
    "overseas_undergrad": ["外国", "外国籍", "留学生", "海外", "国外", "外国の大学", "学位取得証明"],
}

DEGREE_ALIASES = {
    "master": ["修士", "博士前期", "修士課程"],
    "doctor": ["博士", "博士後期", "博士課程"],
}

EXAM_TYPE_ALIASES = {
    "general": ["一般選抜", "一般入試", "一般"],
    "foreign_student": ["外国人留学生", "留学生特別選抜", "私費外国人留学生"],
    "recommended": ["推薦", "推薦入試"],
    "working_adult": ["社会人", "社会人特別選抜"],
}


@dataclass
class ExtractionCursor:
    positive_keywords: list[str] = field(default_factory=list)
    negative_keywords: list[str] = field(default_factory=list)
    global_section_keywords: list[str] = field(default_factory=lambda: list(GLOBAL_SECTION_KEYWORDS))
    section_anchors: list[str] = field(default_factory=list)
    english_aliases: list[str] = field(default_factory=list)
    background_aliases: list[str] = field(default_factory=list)
    degree_aliases: list[str] = field(default_factory=list)
    exam_type_aliases: list[str] = field(default_factory=list)
    include_global_sections: bool = True
    strict_mode: bool = False
    adjacency_window: int = 1

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


def normalize_text(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def chunk_text(chunk: TextChunk) -> str:
    return normalize_text(f"{chunk.title}\n{chunk.text}")


def contains_any(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(keyword and keyword.lower() in lowered for keyword in keywords)


def _other_english_aliases(selected: str) -> list[str]:
    selected = selected.lower()
    return [alias for key, aliases in ENGLISH_ALIASES.items() if key != selected for alias in aliases]


def _other_degree_aliases(selected: str) -> list[str]:
    selected = selected.lower()
    return [alias for key, aliases in DEGREE_ALIASES.items() if key != selected for alias in aliases]


def _other_exam_aliases(selected: str) -> list[str]:
    selected = selected.lower()
    return [alias for key, aliases in EXAM_TYPE_ALIASES.items() if key != selected for alias in aliases]


def build_cursor(profile: ApplicantProfileV2) -> ExtractionCursor:
    english_aliases = ENGLISH_ALIASES.get(profile.english_test.lower(), _list_if(profile.english_test))
    background_aliases = BACKGROUND_ALIASES.get(profile.background, [])
    degree_aliases = DEGREE_ALIASES.get(profile.degree_level.lower(), _list_if(profile.degree_level))
    exam_type_aliases = EXAM_TYPE_ALIASES.get(profile.exam_type.lower(), _list_if(profile.exam_type))
    region_aliases = _list_if(profile.nationality_or_region)

    negative_keywords: list[str] = []
    if profile.english_test:
        negative_keywords.extend(_other_english_aliases(profile.english_test))
    if profile.degree_level:
        negative_keywords.extend(_other_degree_aliases(profile.degree_level))
    if profile.exam_type:
        negative_keywords.extend(_other_exam_aliases(profile.exam_type))

    positive_keywords = _unique(
        [
            *profile.targets,
            *english_aliases,
            *background_aliases,
            *degree_aliases,
            *exam_type_aliases,
            *region_aliases,
            *(_list_if(profile.application_channel)),
        ]
    )

    return ExtractionCursor(
        positive_keywords=positive_keywords,
        negative_keywords=_unique(negative_keywords),
        section_anchors=profile.targets,
        english_aliases=english_aliases,
        background_aliases=_unique([*background_aliases, *region_aliases]),
        degree_aliases=degree_aliases,
        exam_type_aliases=exam_type_aliases,
        include_global_sections=profile.include_global_sections,
        strict_mode=profile.strict_mode,
        adjacency_window=0 if profile.strict_mode else 1,
    )


def _list_if(value: str) -> list[str]:
    return [value] if value else []


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip().lower()
        if not value or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def has_program_marker(text: str) -> bool:
    return contains_any(text, PROGRAM_MARKERS)


def score_chunk(chunk: TextChunk, cursor: ExtractionCursor) -> dict[str, Any]:
    text = chunk_text(chunk)
    score = 0
    reasons: list[str] = []

    if cursor.section_anchors and contains_any(text, cursor.section_anchors):
        score += 7
        reasons.append("matched_section_anchor")
    if cursor.english_aliases and contains_any(text, cursor.english_aliases):
        score += 5
        reasons.append("matched_english_test")
    if cursor.background_aliases and contains_any(text, cursor.background_aliases) and contains_any(text, ACTION_KEYWORDS):
        score += 4
        reasons.append("matched_background")
    if cursor.degree_aliases and contains_any(text, cursor.degree_aliases):
        score += 3
        reasons.append("matched_degree_level")
    if cursor.exam_type_aliases and contains_any(text, cursor.exam_type_aliases):
        score += 3
        reasons.append("matched_exam_type")
    if cursor.include_global_sections and contains_any(text, cursor.global_section_keywords):
        score += 3
        reasons.append("matched_global_section")

    negative_hit = contains_any(text, cursor.negative_keywords)
    if negative_hit:
        score -= 3
        reasons.append("matched_negative_keyword")

    other_program_only = (
        has_program_marker(text)
        and bool(cursor.section_anchors)
        and not contains_any(text, cursor.section_anchors)
        and "matched_english_test" not in reasons
        and "matched_background" not in reasons
    )
    if other_program_only:
        score -= 5
        reasons.append("other_program_only")

    keep = score >= (4 if cursor.strict_mode else 2) and not other_program_only
    return {
        "score": score,
        "keep": keep,
        "reasons": reasons,
        "chars": len(chunk.text),
        "title": chunk.title,
        "pages": chunk.page_numbers,
    }


def select_chunks_by_cursor(
    chunks: list[TextChunk],
    cursor: ExtractionCursor,
) -> tuple[list[TextChunk], list[dict[str, Any]]]:
    decisions: list[dict[str, Any]] = []
    keep_indexes: set[int] = set()

    for index, chunk in enumerate(chunks):
        decision = score_chunk(chunk, cursor)
        decision["index"] = index
        decisions.append(decision)
        if decision["keep"]:
            keep_indexes.add(index)

    if cursor.adjacency_window:
        anchor_indexes = {
            decision["index"]
            for decision in decisions
            if "matched_section_anchor" in decision["reasons"]
        }
        for index in anchor_indexes:
            for adjacent in range(index - cursor.adjacency_window, index + cursor.adjacency_window + 1):
                if 0 <= adjacent < len(chunks):
                    if "other_program_only" in decisions[adjacent]["reasons"]:
                        continue
                    keep_indexes.add(adjacent)
                    if adjacent != index:
                        decisions[adjacent]["keep"] = True
                        decisions[adjacent].setdefault("reasons", []).append("adjacent_to_anchor")

    selected = [chunk for index, chunk in enumerate(chunks) if index in keep_indexes]
    return selected, decisions


def write_cursor_outputs(
    chunks: list[TextChunk],
    decisions: list[dict[str, Any]],
    chunks_output: str | Path,
    decisions_output: str | Path,
) -> None:
    kept_indexes = {decision["index"] for decision in decisions if decision["keep"]}
    Path(chunks_output).parent.mkdir(parents=True, exist_ok=True)
    Path(chunks_output).write_text(
        json.dumps(
            [asdict(chunk) for idx, chunk in enumerate(chunks) if idx in kept_indexes],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    Path(decisions_output).parent.mkdir(parents=True, exist_ok=True)
    Path(decisions_output).write_text(json.dumps(decisions, ensure_ascii=False, indent=2), encoding="utf-8")
