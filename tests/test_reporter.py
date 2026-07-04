from admission_parser.reporter import ApplicantProfile, build_report


def test_report_keeps_general_fees_and_matching_english_requirements():
    data = {
        "university": {"university_name": "東京科学大学"},
        "fees": [
            {
                "amount_yen": 30000,
                "payment_method": "クレジットカード",
                "payment_period": "",
                "notes": "",
                "source_pages": [10],
            }
        ],
        "english_requirements": [
            {
                "test_type": "TOEFL iBT",
                "accepted_variants": ["TOEFL iBT", "TOEFL iBT Home Edition"],
                "rejected_variants": [],
                "minimum_score": "",
                "direct_delivery_required": False,
                "institution_code": "G179",
                "applicable_to": "数学系を除く全系",
                "exceptions": [],
                "condition_logic": "OR",
                "notes": "",
                "source_pages": [11, 12],
            }
        ],
    }
    profile = ApplicantProfile(targets=["情報理工学院"], english_test="toefl", background="cn_undergrad")

    report = build_report(data, profile)

    assert "30,000 日元" in report
    assert "TOEFL iBT" in report
    assert "G179" in report
    assert "未抽取到费用信息" not in report
    assert "未抽取到与该英语考试类型明确匹配的要求" not in report
