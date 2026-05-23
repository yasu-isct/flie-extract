from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .chunker import TextChunk
from .reporter import ApplicantProfile

GENERAL_KEYWORDS = [
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

BACKGROUND_KEYWORDS = {
    "cn_undergrad": ["外国", "外国籍", "留学生", "海外", "国外", "中国", "学位取得証明"],
    "jp_undergrad": ["日本国内", "本学", "高等専門学校", "在学証明"],
    "overseas_undergrad": ["外国", "外国籍", "留学生", "海外", "国外", "学位取得証明"],
}


def normalize_text(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def chunk_text(chunk: TextChunk) -> str:
    return normalize_text(f"{chunk.title}\n{chunk.text}")


def contains_any(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(keyword and keyword.lower() in lowered for keyword in keywords)


def has_program_marker(text: str) -> bool:
    return contains_any(text, PROGRAM_MARKERS)


def chunk_relevance(chunk: TextChunk, profile: ApplicantProfile) -> dict[str, Any]:
    text = chunk_text(chunk)
    target_hit = contains_any(text, profile.targets)
    general_hit = contains_any(text, GENERAL_KEYWORDS)

    english_aliases = ENGLISH_ALIASES.get(profile.english_test.lower(), [profile.english_test])
    english_hit = bool(profile.english_test and contains_any(text, english_aliases))

    background_terms = BACKGROUND_KEYWORDS.get(profile.background, [])
    background_hit = bool(
        profile.background
        and contains_any(text, background_terms)
        and contains_any(text, ACTION_KEYWORDS)
    )

    program_marker = has_program_marker(text)
    other_program_only = program_marker and not target_hit and not general_hit and not english_hit and not background_hit

    score = 0
    reasons = []
    if target_hit:
        score += 5
        reasons.append("target")
    if english_hit:
        score += 4
        reasons.append("english")
    if background_hit:
        score += 3
        reasons.append("background")
    if general_hit:
        score += 2
        reasons.append("general")
    if other_program_only:
        score -= 4
        reasons.append("other_program")

    return {
        "score": score,
        "keep": score >= 2 and not other_program_only,
        "reasons": reasons,
        "chars": len(chunk.text),
        "title": chunk.title,
        "pages": chunk.page_numbers,
    }


def filter_chunks(chunks: list[TextChunk], profile: ApplicantProfile) -> tuple[list[TextChunk], list[dict[str, Any]]]:
    kept: list[TextChunk] = []
    decisions: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks):
        decision = chunk_relevance(chunk, profile)
        decision["index"] = index
        decisions.append(decision)
        if decision["keep"]:
            kept.append(chunk)
    return kept, decisions


def write_filtered_chunks(
    chunks: list[TextChunk],
    decisions: list[dict[str, Any]],
    chunks_output: str | Path,
    summary_output: str | Path,
) -> None:
    kept_indexes = {decision["index"] for decision in decisions if decision["keep"]}
    Path(chunks_output).parent.mkdir(parents=True, exist_ok=True)
    Path(chunks_output).write_text(
        json.dumps([asdict(chunk) for idx, chunk in enumerate(chunks) if idx in kept_indexes], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    Path(summary_output).parent.mkdir(parents=True, exist_ok=True)
    Path(summary_output).write_text(json.dumps(decisions, ensure_ascii=False, indent=2), encoding="utf-8")
