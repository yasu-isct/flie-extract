from argparse import Namespace

from admission_parser.profile_input import profile_from_args, profile_from_mapping


def test_profile_mapping_builds_combined_targets():
    profile = profile_from_mapping(
        {
            "target_college": ["情報理工学院"],
            "target_department": ["情報工学系"],
            "english_test": "toefl",
        }
    )
    assert profile.targets == ["情報理工学院", "情報工学系"]
    assert profile.english_test == "toefl"


def test_cli_profile_overrides_config(tmp_path):
    config = tmp_path / "profile.yaml"
    config.write_text("english_test: toeic\nbackground: jp_undergrad\n", encoding="utf-8")
    args = Namespace(
        profile_config=str(config),
        interactive=False,
        target=[],
        target_college=[],
        target_department=["情報工学系"],
        target_program=[],
        degree_level="",
        exam_type="",
        english_test="toefl",
        background="",
        nationality_or_region="",
        application_channel="",
        strict_mode=False,
        no_global_sections=False,
    )
    profile = profile_from_args(args)
    assert profile.target_department == ["情報工学系"]
    assert profile.english_test == "toefl"
    assert profile.background == "jp_undergrad"
