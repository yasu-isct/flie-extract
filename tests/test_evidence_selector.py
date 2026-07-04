from admission_parser.chunker import TextChunk
from admission_parser.evidence_selector import (
    build_evidence_selector,
    select_chunks_by_evidence_selector,
)
from admission_parser.profile_input import ApplicantProfileV2


def test_evidence_selector_keeps_target_and_global_chunks():
    chunks = [
        TextChunk("x.pdf", [1], "工学院", "電気電子系の試験日程"),
        TextChunk("x.pdf", [2], "出願期間", "出願期間は6月1日から6月10日まで。必着。"),
        TextChunk("x.pdf", [3], "情報理工学院", "情報工学系の提出書類"),
    ]
    profile = ApplicantProfileV2(
        target_college=["情報理工学院"],
        target_department=["情報工学系"],
        include_global_sections=True,
    )
    selected, decisions = select_chunks_by_evidence_selector(chunks, build_evidence_selector(profile))
    assert [chunk.page_numbers for chunk in selected] == [[2], [3]]
    assert decisions[0]["keep"] is False
    assert "matched_global_section" in decisions[1]["reasons"]
    assert "matched_section_anchor" in decisions[2]["reasons"]


def test_strict_evidence_selector_does_not_keep_adjacent_noise():
    chunks = [
        TextChunk("x.pdf", [1], "情報理工学院", "情報工学系"),
        TextChunk("x.pdf", [2], "雑項", "これは隣接しているだけの文です。"),
    ]
    profile = ApplicantProfileV2(target_department=["情報工学系"], strict_mode=True)
    selected, decisions = select_chunks_by_evidence_selector(chunks, build_evidence_selector(profile))
    assert len(selected) == 1
    assert decisions[1]["keep"] is False


def test_evidence_selector_adds_english_aliases_and_negative_terms():
    profile = ApplicantProfileV2(english_test="toefl")
    selector = build_evidence_selector(profile)
    assert "TOEFL iBT" in selector.english_aliases
    assert "TOEIC" in selector.negative_keywords
