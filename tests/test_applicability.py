from admission_parser.applicability import (
    BaseReasoningChainsResult,
    BaseReasoningChain,
    ReasoningEvidence,
    BaseFactsResult,
    ApplicabilityResult,
    NarrativeReportResult,
    evaluate_applicability,
    generate_base_facts,
    generate_base_reasoning_chains,
    generate_narrative_report,
    document_facts_payload,
    stable_payload,
)
from admission_parser.profile_input import ApplicantProfileV2


class FakeCompletions:
    def __init__(self):
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        response_model = kwargs["response_model"]
        if response_model is BaseFactsResult:
            return BaseFactsResult(
                document_summary="募集要项包含英语考试、材料和日程规则。",
                uncertainties=["目标系细则需要确认"],
            )
        if response_model is BaseReasoningChainsResult:
            return BaseReasoningChainsResult(
                chains=[
                    BaseReasoningChain(
                        question="英语考试规则是什么？",
                        answer="文档接受 TOEIC 或 TOEFL，需确认各系细则。",
                        confidence="medium",
                        reasoning_steps=["结构化 JSON 中存在英语考试要求。"],
                        evidence=[ReasoningEvidence(source_pages=[5], quote="TOEIC L&R")],
                        uncertainty="目标系细则需要确认。",
                    )
                ],
                open_questions=["目标系是否有单独英语要求？"],
            )
        if response_model is ApplicabilityResult:
            return ApplicabilityResult(
                profile_summary="中国本科背景，目标情報工学系",
                likely_eligibility="海外大学毕业并取得学位",
                next_actions=["确认最终出願資格编号"],
            )
        if response_model is NarrativeReportResult:
            return NarrativeReportResult(report_markdown="# 个性化报告\n\n请确认出願資格。")
        raise AssertionError(response_model)


class FakeChat:
    def __init__(self):
        self.completions = FakeCompletions()


class FakeClient:
    def __init__(self):
        self.chat = FakeChat()


def test_applicability_and_narrative_report_use_cache(tmp_path, monkeypatch):
    fake_client = FakeClient()
    monkeypatch.setattr("admission_parser.applicability._client", lambda: fake_client)
    profile = ApplicantProfileV2(
        target_department=["情報工学系"],
        english_test="toefl",
        background="cn_undergrad",
    )
    structured = {
        "english_requirements": [
            {
                "test_type": "TOEFL iBT",
                "applicable_to": "数学系を除く全系",
                "source_pages": [11, 12],
            }
        ]
    }

    first_applicability = evaluate_applicability(structured, profile, cache_dir=tmp_path)
    second_applicability = evaluate_applicability(structured, profile, cache_dir=tmp_path)
    first_report = generate_narrative_report(
        structured,
        profile,
        first_applicability,
        cache_dir=tmp_path,
    )
    second_report = generate_narrative_report(
        structured,
        profile,
        first_applicability,
        cache_dir=tmp_path,
    )

    assert fake_client.chat.completions.calls == 2
    assert first_applicability.likely_eligibility == second_applicability.likely_eligibility
    assert "# 个性化报告" in first_report.report_markdown
    assert first_report.report_markdown == second_report.report_markdown
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_stable_payload_removes_runtime_metadata():
    payload = {
        "english_requirements": [{"test_type": "TOEIC", "source_pages": [1]}],
        "_profile": {
            "target_college": ["環境・社会理工学院"],
            "llm_cache_dir": "outputs/llm_cache",
            "llm_cache_hits": 8,
            "llm_cache_misses": 0,
            "runtime_seconds": 12.3,
        },
        "_artifacts": {
            "structured_json": "outputs/runs/a/07_structured.json",
            "llm_report": "outputs/runs/a/10_llm_report.md",
        },
    }

    stable = stable_payload(payload)

    assert stable == {
        "english_requirements": [{"test_type": "TOEIC", "source_pages": [1]}],
        "_profile": {
            "target_college": ["環境・社会理工学院"],
        },
    }


def test_document_facts_payload_excludes_profile_and_derived_fields():
    structured = {
        "required_documents": [{"name": "成績証明書", "source_pages": [3]}],
        "english_requirements": [{"test_type": "TOEIC", "source_pages": [5]}],
        "_profile": {"english_test": "toeic"},
        "_user_requirements": {"english_test": "toeic"},
        "_retrieval": {"queries": ["TOEIC"]},
        "_base_facts": {"document_summary": "old"},
        "_applicability": {"profile_summary": "old"},
    }

    assert document_facts_payload(structured) == {
        "required_documents": [{"name": "成績証明書", "source_pages": [3]}],
        "english_requirements": [{"test_type": "TOEIC", "source_pages": [5]}],
    }


def test_base_facts_cache_ignores_profile_metadata(tmp_path, monkeypatch):
    fake_client = FakeClient()
    monkeypatch.setattr("admission_parser.applicability._client", lambda: fake_client)
    structured_toeic = {
        "english_requirements": [{"test_type": "TOEIC", "source_pages": [5]}],
        "_profile": {"english_test": "toeic", "llm_cache_hits": 0},
    }
    structured_toefl = {
        "english_requirements": [{"test_type": "TOEIC", "source_pages": [5]}],
        "_profile": {"english_test": "toefl", "llm_cache_hits": 8},
    }

    first = generate_base_facts(structured_toeic, cache_dir=tmp_path)
    second = generate_base_facts(structured_toefl, cache_dir=tmp_path)

    assert fake_client.chat.completions.calls == 1
    assert first.document_summary == second.document_summary
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_base_reasoning_chains_cache_ignores_profile_metadata(tmp_path, monkeypatch):
    fake_client = FakeClient()
    monkeypatch.setattr("admission_parser.applicability._client", lambda: fake_client)
    base_facts = BaseFactsResult(document_summary="英语规则已抽取。")
    structured_toeic = {
        "english_requirements": [{"test_type": "TOEIC", "source_pages": [5]}],
        "_profile": {"english_test": "toeic"},
    }
    structured_toefl = {
        "english_requirements": [{"test_type": "TOEIC", "source_pages": [5]}],
        "_profile": {"english_test": "toefl"},
    }

    first = generate_base_reasoning_chains(
        structured_toeic,
        base_facts=base_facts,
        cache_dir=tmp_path,
    )
    second = generate_base_reasoning_chains(
        structured_toefl,
        base_facts=base_facts,
        cache_dir=tmp_path,
    )

    assert fake_client.chat.completions.calls == 1
    assert first.chains[0].answer == second.chains[0].answer
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_applicability_cache_ignores_runtime_metadata(tmp_path, monkeypatch):
    fake_client = FakeClient()
    monkeypatch.setattr("admission_parser.applicability._client", lambda: fake_client)
    profile = ApplicantProfileV2(target_department=["情報工学系"])
    structured_first = {
        "required_documents": [{"name": "成績証明書", "source_pages": [3]}],
        "_profile": {
            "selected_chunks": 10,
            "llm_cache_hits": 0,
            "llm_cache_misses": 8,
        },
        "_artifacts": {"structured_json": "outputs/runs/first/07_structured.json"},
    }
    structured_second = {
        "required_documents": [{"name": "成績証明書", "source_pages": [3]}],
        "_profile": {
            "selected_chunks": 10,
            "llm_cache_hits": 8,
            "llm_cache_misses": 0,
        },
        "_artifacts": {"structured_json": "outputs/runs/second/07_structured.json"},
    }

    first = evaluate_applicability(structured_first, profile, cache_dir=tmp_path)
    second = evaluate_applicability(structured_second, profile, cache_dir=tmp_path)

    assert fake_client.chat.completions.calls == 1
    assert first.likely_eligibility == second.likely_eligibility
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_applicability_uses_cached_base_facts_across_profile_changes(tmp_path, monkeypatch):
    fake_client = FakeClient()
    monkeypatch.setattr("admission_parser.applicability._client", lambda: fake_client)
    structured = {
        "english_requirements": [
            {
                "test_type": "TOEIC",
                "applicable_to": "数学系を除く全系",
                "source_pages": [5],
            }
        ]
    }
    toeic_profile = ApplicantProfileV2(target_department=["環境工学系"], english_test="toeic")
    toefl_profile = ApplicantProfileV2(target_department=["環境工学系"], english_test="toefl")

    first_base_facts = generate_base_facts(structured, cache_dir=tmp_path)
    second_base_facts = generate_base_facts(structured, cache_dir=tmp_path)
    first_reasoning = generate_base_reasoning_chains(
        structured,
        base_facts=first_base_facts,
        cache_dir=tmp_path,
    )
    second_reasoning = generate_base_reasoning_chains(
        structured,
        base_facts=second_base_facts,
        cache_dir=tmp_path,
    )
    evaluate_applicability(
        structured,
        toeic_profile,
        base_facts=first_base_facts,
        base_reasoning_chains=first_reasoning,
        cache_dir=tmp_path,
    )
    evaluate_applicability(
        structured,
        toefl_profile,
        base_facts=second_base_facts,
        base_reasoning_chains=second_reasoning,
        cache_dir=tmp_path,
    )

    # One base-facts call, one base-reasoning call, plus two profile-specific calls.
    assert fake_client.chat.completions.calls == 4
    assert len(list(tmp_path.glob("*.json"))) == 4


def test_narrative_report_cache_ignores_runtime_metadata(tmp_path, monkeypatch):
    fake_client = FakeClient()
    monkeypatch.setattr("admission_parser.applicability._client", lambda: fake_client)
    profile = ApplicantProfileV2(target_department=["情報工学系"])
    applicability = ApplicabilityResult(
        profile_summary="日本本科背景",
        key_warnings=["确认目标系细则"],
    )
    structured_first = {
        "exam_schedules": [{"event": "口述試験", "source_pages": [5]}],
        "_profile": {"llm_cache_hits": 0, "llm_cache_misses": 3},
        "_artifacts": {"llm_report": "outputs/runs/first/10_llm_report.md"},
    }
    structured_second = {
        "exam_schedules": [{"event": "口述試験", "source_pages": [5]}],
        "_profile": {"llm_cache_hits": 3, "llm_cache_misses": 0},
        "_artifacts": {"llm_report": "outputs/runs/second/10_llm_report.md"},
    }

    first = generate_narrative_report(
        structured_first,
        profile,
        applicability=applicability,
        cache_dir=tmp_path,
    )
    second = generate_narrative_report(
        structured_second,
        profile,
        applicability=applicability,
        cache_dir=tmp_path,
    )

    assert fake_client.chat.completions.calls == 1
    assert first.report_markdown == second.report_markdown
    assert len(list(tmp_path.glob("*.json"))) == 1
