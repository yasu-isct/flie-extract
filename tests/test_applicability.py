from admission_parser.applicability import (
    ApplicabilityResult,
    NarrativeReportResult,
    evaluate_applicability,
    generate_narrative_report,
)
from admission_parser.profile_input import ApplicantProfileV2


class FakeCompletions:
    def __init__(self):
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        response_model = kwargs["response_model"]
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
