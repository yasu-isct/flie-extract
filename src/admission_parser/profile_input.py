from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .reporter import ApplicantProfile


@dataclass
class ApplicantProfileV2:
    target_college: list[str] = field(default_factory=list)
    target_department: list[str] = field(default_factory=list)
    target_program: list[str] = field(default_factory=list)
    degree_level: str = ""
    exam_type: str = ""
    english_test: str = ""
    background: str = ""
    nationality_or_region: str = ""
    application_channel: str = ""
    include_global_sections: bool = True
    strict_mode: bool = False
    legacy_targets: list[str] = field(default_factory=list)

    @property
    def targets(self) -> list[str]:
        return _unique(
            [
                *self.legacy_targets,
                *self.target_college,
                *self.target_department,
                *self.target_program,
            ]
        )

    def to_report_profile(self) -> ApplicantProfile:
        return ApplicantProfile(
            targets=self.targets,
            english_test=self.english_test,
            background=self.background,
        )

    def model_dump(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["targets"] = self.targets
        return payload


def _listify(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _boolify(value: Any, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip().lower()
        if not value or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def default_profile() -> ApplicantProfileV2:
    return ApplicantProfileV2()


def load_profile_config(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Profile config not found: {config_path}")
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("Profile config must be a mapping.")
    return data


def profile_from_mapping(data: dict[str, Any]) -> ApplicantProfileV2:
    return ApplicantProfileV2(
        target_college=_listify(data.get("target_college")),
        target_department=_listify(data.get("target_department")),
        target_program=_listify(data.get("target_program")),
        degree_level=_stringify(data.get("degree_level")),
        exam_type=_stringify(data.get("exam_type")),
        english_test=_stringify(data.get("english_test")),
        background=_stringify(data.get("background")),
        nationality_or_region=_stringify(data.get("nationality_or_region")),
        application_channel=_stringify(data.get("application_channel")),
        include_global_sections=_boolify(data.get("include_global_sections"), True),
        strict_mode=_boolify(data.get("strict_mode"), False),
        legacy_targets=_listify(data.get("target") or data.get("targets")),
    )


def merge_profiles(base: ApplicantProfileV2, override: ApplicantProfileV2) -> ApplicantProfileV2:
    return ApplicantProfileV2(
        target_college=override.target_college or base.target_college,
        target_department=override.target_department or base.target_department,
        target_program=override.target_program or base.target_program,
        degree_level=override.degree_level or base.degree_level,
        exam_type=override.exam_type or base.exam_type,
        english_test=override.english_test or base.english_test,
        background=override.background or base.background,
        nationality_or_region=override.nationality_or_region or base.nationality_or_region,
        application_channel=override.application_channel or base.application_channel,
        include_global_sections=override.include_global_sections,
        strict_mode=override.strict_mode,
        legacy_targets=override.legacy_targets or base.legacy_targets,
    )


def add_profile_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--profile-config", default=None, help="YAML/JSON applicant profile config.")
    parser.add_argument("--interactive", action="store_true", help="Prompt for missing applicant profile fields.")
    parser.add_argument("--target", action="append", default=[], help="Legacy target keyword. Can repeat.")
    parser.add_argument("--target-college", action="append", default=[])
    parser.add_argument("--target-department", action="append", default=[])
    parser.add_argument("--target-program", action="append", default=[])
    parser.add_argument("--degree-level", default="", choices=["", "master", "doctor"])
    parser.add_argument(
        "--exam-type",
        default="",
        choices=["", "general", "foreign_student", "recommended", "working_adult"],
    )
    parser.add_argument("--english-test", default="", choices=["", "toefl", "toeic", "ielts"])
    parser.add_argument(
        "--background",
        default="",
        choices=["", "cn_undergrad", "jp_undergrad", "overseas_undergrad"],
    )
    parser.add_argument("--nationality-or-region", default="")
    parser.add_argument("--application-channel", default="")
    parser.add_argument("--strict-mode", action="store_true")
    parser.add_argument("--no-global-sections", action="store_true")


def profile_from_args(args: argparse.Namespace) -> ApplicantProfileV2:
    config = profile_from_mapping(load_profile_config(args.profile_config))
    cli = ApplicantProfileV2(
        target_college=_listify(args.target_college),
        target_department=_listify(args.target_department),
        target_program=_listify(args.target_program),
        degree_level=args.degree_level,
        exam_type=args.exam_type,
        english_test=args.english_test,
        background=args.background,
        nationality_or_region=args.nationality_or_region,
        application_channel=args.application_channel,
        include_global_sections=not args.no_global_sections,
        strict_mode=args.strict_mode,
        legacy_targets=_listify(args.target),
    )
    profile = merge_profiles(config, cli)
    if args.interactive:
        profile = prompt_for_profile(profile)
    return profile


def _ask(label: str, current: str = "") -> str:
    suffix = f" [{current}]" if current else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or current


def _ask_list(label: str, current: list[str]) -> list[str]:
    current_text = ", ".join(current)
    suffix = f" [{current_text}]" if current_text else ""
    value = input(f"{label}{suffix}: ").strip()
    return _listify(value) or current


def prompt_for_profile(profile: ApplicantProfileV2) -> ApplicantProfileV2:
    return ApplicantProfileV2(
        target_college=_ask_list("目标学院，逗号分隔，留空表示不指定", profile.target_college),
        target_department=_ask_list("目标系/专攻，逗号分隔，留空表示不指定", profile.target_department),
        target_program=_ask_list("目标课程/项目，逗号分隔，留空表示不指定", profile.target_program),
        degree_level=_ask("申请层级 master/doctor，留空表示不指定", profile.degree_level),
        exam_type=_ask("入试类型 general/foreign_student/recommended/working_adult，留空表示不指定", profile.exam_type),
        english_test=_ask("英语考试 toefl/toeic/ielts，留空表示不指定", profile.english_test),
        background=_ask("申请背景 cn_undergrad/jp_undergrad/overseas_undergrad，留空表示不指定", profile.background),
        nationality_or_region=_ask("国籍/地区，例如 china，留空表示不指定", profile.nationality_or_region),
        application_channel=_ask("申请方式 online/post/mail，留空表示不指定", profile.application_channel),
        include_global_sections=profile.include_global_sections,
        strict_mode=profile.strict_mode,
        legacy_targets=profile.legacy_targets,
    )
