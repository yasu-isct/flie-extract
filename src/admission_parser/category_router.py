from __future__ import annotations

from collections import Counter

from .chunker import TextChunk

CATEGORY_KEYWORDS = {
    "english": ["TOEFL", "TOEIC", "IELTS", "英語", "外部試験", "スコア"],
    "fees": ["検定料", "入学検定料", "支払", "クレジット", "振込", "円", "免除"],
    "documents": ["提出書類", "出願書類", "証明書", "志願票", "推薦書", "成績証明", "卒業証明"],
    "periods": ["出願期間", "提出期限", "締切", "必着", "消印有効", "登録期間"],
    "exams": ["試験", "口述", "筆答", "面接", "合格発表", "受験票"],
    "methods": ["出願方法", "郵送", "オンライン", "インターネット出願", "持参", "宛名"],
}

FOCUS_INSTRUCTIONS = {
    "english": "Focus only on English test requirements. Fill english_requirements; keep unrelated lists empty unless directly needed.",
    "fees": "Focus only on application fees and payment rules. Fill fees; keep unrelated lists empty unless directly needed.",
    "documents": "Focus only on required documents and document conditions. Fill required_documents; keep unrelated lists empty unless directly needed.",
    "periods": "Focus only on application periods, deadlines, and must-arrive/postmark rules. Fill application_periods; keep unrelated lists empty unless directly needed.",
    "exams": "Focus only on exam schedules, admission events, result announcements, and test locations. Fill exam_schedules; keep unrelated lists empty unless directly needed.",
    "methods": "Focus only on submission/application methods, destinations, online registration, and postal rules. Fill submission_methods; keep unrelated lists empty unless directly needed.",
    "general": "Extract only clearly stated admission information. Avoid warnings for irrelevant text.",
}


def categorize_chunk(chunk: TextChunk) -> str:
    text = f"{chunk.title}\n{chunk.text}"
    scores: Counter[str] = Counter()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                scores[category] += 1
    if not scores:
        return "general"
    return scores.most_common(1)[0][0]


def focus_instruction(category: str) -> str:
    return FOCUS_INSTRUCTIONS.get(category, FOCUS_INSTRUCTIONS["general"])


def category_counts(chunks: list[TextChunk]) -> dict[str, int]:
    counts: Counter[str] = Counter(categorize_chunk(chunk) for chunk in chunks)
    return dict(sorted(counts.items()))
