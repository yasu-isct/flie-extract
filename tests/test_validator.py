from admission_parser.schemas import AdmissionInfo, ApplicationPeriod, DeadlineRule
from admission_parser.validator import convert_era_date, validate_admission_info


def test_convert_era_date():
    assert convert_era_date("令和8年5月20日") == "2026-05-20"
    assert convert_era_date("平成31年4月30日") == "2019-04-30"


def test_validate_period_order():
    info = AdmissionInfo(
        application_periods=[
            ApplicationPeriod(
                period_type="出願期間",
                start_date="2026-07-10",
                end_date="2026-07-01",
                deadline_rule=DeadlineRule.must_arrive,
            )
        ]
    )
    errors = validate_admission_info(info)
    assert errors
