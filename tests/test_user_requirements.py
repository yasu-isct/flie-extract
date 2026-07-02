from admission_parser.profile_input import ApplicantProfileV2
from admission_parser.user_requirements import build_user_requirements, enrich_json_with_requirements


def test_build_user_requirements_creates_action_items():
    data = {
        "application_periods": [
            {
                "period_type": "出願期間",
                "start_date": "2026-06-01",
                "end_date": "2026-06-10",
                "deadline_rule": "必着",
            }
        ],
        "required_documents": [
            {"name": "成績証明書", "conditions": ""},
            {"name": "在留カード", "conditions": "外国籍の志願者"},
        ],
        "english_requirements": [{"test_type": "TOEFL iBT", "notes": "直送要否を確認"}],
        "fees": [{"amount_yen": 30000}],
        "exam_schedules": [{"exam_type": "口述試験", "date": "2026-08-01"}],
    }
    profile = ApplicantProfileV2(english_test="toefl", background="cn_undergrad")
    requirements = build_user_requirements(data, profile)
    assert requirements["summary"]["deadline_count"] == 1
    assert requirements["summary"]["required_document_count"] == 1
    assert requirements["summary"]["conditional_document_count"] == 1
    assert any(item["type"] == "deadline" for item in requirements["action_items"])


def test_enrich_json_with_requirements_writes_output(tmp_path):
    source = tmp_path / "parsed.json"
    output = tmp_path / "requirements.json"
    source.write_text(
        '{"application_periods":[{"period_type":"出願期間","end_date":"2026-06-10"}]}',
        encoding="utf-8",
    )
    payload = enrich_json_with_requirements(source, ApplicantProfileV2(), output=output)
    assert output.exists()
    assert "_user_requirements" in payload
