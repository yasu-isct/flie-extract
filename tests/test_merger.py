from admission_parser.merger import merge_admission_infos, warning_to_structured
from admission_parser.schemas import (
    AdmissionInfo,
    ApplicationPeriod,
    DeadlineRule,
    EnglishRequirement,
    RequiredDocument,
)


def test_merge_similar_application_periods():
    info = merge_admission_infos(
        [
            AdmissionInfo(
                application_periods=[
                    ApplicationPeriod(
                        period_type="出願期間",
                        start_date="2026-06-04",
                        end_date="2026-06-10",
                        deadline_rule=DeadlineRule.must_arrive,
                        notes="インターネット出願サイトでの登録は、6月1日午前9時から可能。",
                    )
                ]
            ),
            AdmissionInfo(
                application_periods=[
                    ApplicationPeriod(
                        period_type="出願期間",
                        start_date="2026-06-04",
                        end_date="2026-06-10",
                        deadline_rule=DeadlineRule.must_arrive,
                        notes="インターネット出願サイトによる出願情報の登録は6月1日午前9時から可能。",
                    )
                ]
            ),
        ]
    )
    assert len(info.application_periods) == 1


def test_merge_same_document_with_conditions():
    info = merge_admission_infos(
        [
            AdmissionInfo(required_documents=[RequiredDocument(name="成績証明書", conditions="全員")]),
            AdmissionInfo(required_documents=[RequiredDocument(name="成績証明書", conditions="外国大学出身者")]),
        ]
    )
    assert len(info.required_documents) == 1
    assert "全員" in info.required_documents[0].conditions
    assert "外国大学出身者" in info.required_documents[0].conditions


def test_merge_english_variants():
    info = merge_admission_infos(
        [
            AdmissionInfo(
                english_requirements=[
                    EnglishRequirement(test_type="TOEFL iBT", accepted_variants=["TOEFL iBT"])
                ]
            ),
            AdmissionInfo(
                english_requirements=[
                    EnglishRequirement(
                        test_type="TOEFL iBT Home Edition",
                        accepted_variants=["TOEFL iBT Home Edition"],
                        institution_code="G179",
                    )
                ]
            ),
        ]
    )
    assert len(info.english_requirements) == 1
    assert "TOEFL iBT" in info.english_requirements[0].accepted_variants
    assert "TOEFL iBT Home Edition" in info.english_requirements[0].accepted_variants
    assert info.english_requirements[0].institution_code == "G179"


def test_merge_english_condition_logic_keeps_valid_literal():
    info = merge_admission_infos(
        [
            AdmissionInfo(english_requirements=[EnglishRequirement(test_type="TOEFL iBT")]),
            AdmissionInfo(
                english_requirements=[
                    EnglishRequirement(test_type="TOEFL iBT Home Edition", condition_logic="AND")
                ]
            ),
        ]
    )
    assert len(info.english_requirements) == 1
    assert info.english_requirements[0].condition_logic == "AND"


def test_warning_to_structured():
    warning = warning_to_structured("未找到考试日程信息")
    assert warning.field == "exam_schedules"
    assert warning.message == "未找到考试日程信息"
