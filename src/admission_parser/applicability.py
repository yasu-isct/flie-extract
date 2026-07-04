from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

from .profile_input import ApplicantProfileV2, add_profile_arguments, profile_from_args
from .utils import ensure_dir, write_json

APPLICABILITY_PROMPT_VERSION = "applicability_v2"
NARRATIVE_REPORT_PROMPT_VERSION = "narrative_report_v2"


class ApplicabilityDecision(BaseModel):
    item_type: Literal[
        "deadline",
        "submission_method",
        "required_document",
        "exam_schedule",
        "fee",
        "english_requirement",
        "warning",
        "other",
    ] = "other"
    title: str = ""
    applies_to_profile: Literal["yes", "no", "uncertain"] = "uncertain"
    reason: str = Field("", description="Chinese explanation grounded in the JSON/source text.")
    action: str = Field("", description="Chinese action item for the applicant, if any.")
    source_pages: list[int] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class ApplicabilityResult(BaseModel):
    profile_summary: str = ""
    likely_eligibility: str = ""
    required_items: list[ApplicabilityDecision] = Field(default_factory=list)
    not_applicable_items: list[ApplicabilityDecision] = Field(default_factory=list)
    uncertain_items: list[ApplicabilityDecision] = Field(default_factory=list)
    key_warnings: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class NarrativeReportResult(BaseModel):
    report_markdown: str = Field("", description="Chinese Markdown report.")
    caveats: list[str] = Field(default_factory=list)


APPLICABILITY_SYSTEM_PROMPT = """
你是日本大学院募集要项的适用性判定专家。你会收到已经结构化抽取后的 JSON 和申请者画像。
你的任务不是重新抽取 PDF，而是判断已有条目是否适用于该申请者。
必须只使用输入 JSON 中存在的信息；不要编造日期、金额、条件、系名或材料。
需要特别理解日语条件表达，例如「全系」「全学院」「を除く」「のみ」「及び」「又は」「ただし」「出願資格(1)～(8)」。
不要根据“外国大学毕业”“中国本科”等背景自动推断具体出願資格编号；只有输入 JSON 明确包含条款编号和条款内容映射时，才可以给出编号。
如果无法从输入确定用户最终属于哪一个出願資格，必须标记 uncertain，并说明需要人工确认。
每个重要判断都要尽量保留 source_pages 和 evidence。
输出必须是中文；证据片段可以保留原文日文。
""".strip()

NARRATIVE_REPORT_SYSTEM_PROMPT = """
你是面向中国申请者的日本大学院募集要项报告撰写助手。
你会收到结构化 JSON、申请者画像，以及可选的适用性判定 JSON。
请写一份自然、清晰、可执行的中文 Markdown 报告。
必须以输入 JSON 为唯一事实来源；不要编造没有出现的日期、金额、材料、分数或条件。
关键日期、费用、英语要求、材料、考试日程和风险提示应带 source_pages 或页码提示。
不要把申请者背景自动映射成具体出願資格编号；除非适用性判定 JSON 已经明确给出有证据支持的编号。
遇到适用性不确定的内容，要明确写“需要确认”，不要硬判。
语气应像认真负责的申请顾问，但保持可追溯和克制。
""".strip()


def _client():
    load_dotenv()
    try:
        import instructor
    except ImportError as exc:
        raise RuntimeError("instructor is not installed. Run `pip install -e .[dev]`.") from exc
    base_url = os.getenv("OPENAI_BASE_URL")
    client = OpenAI(base_url=base_url) if base_url else OpenAI()
    mode_name = os.getenv("INSTRUCTOR_MODE", "JSON").upper()
    mode = getattr(instructor.Mode, mode_name, instructor.Mode.JSON)
    return instructor.from_openai(client, mode=mode)


def _model(model: str | None = None) -> str:
    load_dotenv()
    return model or os.getenv("OPENAI_REPORT_MODEL") or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")


def _compact_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _cache_key(kind: str, prompt_version: str, model: str, payload: dict[str, Any]) -> str:
    raw = _compact_json(
        {
            "kind": kind,
            "prompt_version": prompt_version,
            "model": model,
            "payload": payload,
        }
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _load_cache(cache_dir: str | Path | None, key: str, response_model: type[BaseModel]) -> BaseModel | None:
    if not cache_dir:
        return None
    path = Path(cache_dir) / f"{key}.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return response_model.model_validate(payload["result"])


def _write_cache(
    cache_dir: str | Path | None,
    key: str,
    result: BaseModel,
    kind: str,
    prompt_version: str,
    model: str,
) -> None:
    if not cache_dir:
        return
    path = Path(cache_dir) / f"{key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "manifest": {
                    "kind": kind,
                    "prompt_version": prompt_version,
                    "model": model,
                    "response_model": type(result).__name__,
                },
                "result": result.model_dump(mode="json"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _profile_payload(profile: ApplicantProfileV2) -> dict[str, Any]:
    return profile.model_dump()


def evaluate_applicability(
    structured: dict[str, Any],
    profile: ApplicantProfileV2,
    model: str | None = None,
    cache_dir: str | Path | None = Path("outputs") / "llm_cache",
) -> ApplicabilityResult:
    selected_model = _model(model)
    payload = {
        "profile": _profile_payload(profile),
        "structured": structured,
    }
    key = _cache_key("applicability", APPLICABILITY_PROMPT_VERSION, selected_model, payload)
    cached = _load_cache(cache_dir, key, ApplicabilityResult)
    if cached is not None:
        return cached

    user_prompt = (
        "请基于以下申请者画像和结构化募集要项 JSON，判断各条目是否适用于该申请者。\n\n"
        f"申请者画像:\n{json.dumps(_profile_payload(profile), ensure_ascii=False, indent=2)}\n\n"
        f"结构化 JSON:\n{json.dumps(structured, ensure_ascii=False, indent=2)}"
    )
    result = _client().chat.completions.create(
        model=selected_model,
        response_model=ApplicabilityResult,
        messages=[
            {"role": "system", "content": APPLICABILITY_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        max_retries=2,
    )
    _write_cache(cache_dir, key, result, "applicability", APPLICABILITY_PROMPT_VERSION, selected_model)
    return result


def generate_narrative_report(
    structured: dict[str, Any],
    profile: ApplicantProfileV2,
    applicability: ApplicabilityResult | dict[str, Any] | None = None,
    model: str | None = None,
    cache_dir: str | Path | None = Path("outputs") / "llm_cache",
) -> NarrativeReportResult:
    selected_model = _model(model)
    applicability_payload = (
        applicability.model_dump(mode="json")
        if isinstance(applicability, ApplicabilityResult)
        else applicability
    )
    payload = {
        "profile": _profile_payload(profile),
        "structured": structured,
        "applicability": applicability_payload or {},
    }
    key = _cache_key("narrative_report", NARRATIVE_REPORT_PROMPT_VERSION, selected_model, payload)
    cached = _load_cache(cache_dir, key, NarrativeReportResult)
    if cached is not None:
        return cached

    user_prompt = (
        "请基于以下数据生成自然语言 Markdown 报告。\n\n"
        f"申请者画像:\n{json.dumps(_profile_payload(profile), ensure_ascii=False, indent=2)}\n\n"
        f"结构化 JSON:\n{json.dumps(structured, ensure_ascii=False, indent=2)}\n\n"
        f"适用性判定 JSON:\n{json.dumps(applicability_payload or {}, ensure_ascii=False, indent=2)}"
    )
    result = _client().chat.completions.create(
        model=selected_model,
        response_model=NarrativeReportResult,
        messages=[
            {"role": "system", "content": NARRATIVE_REPORT_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        max_retries=2,
    )
    _write_cache(cache_dir, key, result, "narrative_report", NARRATIVE_REPORT_PROMPT_VERSION, selected_model)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LLM applicability and narrative report passes.")
    parser.add_argument("structured_json")
    parser.add_argument("--applicability-output", default=None)
    parser.add_argument("--llm-report-output", default=None)
    parser.add_argument("--skip-applicability", action="store_true")
    parser.add_argument("--skip-llm-report", action="store_true")
    parser.add_argument("--llm-cache-dir", default=str(Path("outputs") / "llm_cache"))
    parser.add_argument("--model", default=None)
    add_profile_arguments(parser)
    args = parser.parse_args()

    profile = profile_from_args(args)
    structured_path = Path(args.structured_json)
    structured = json.loads(structured_path.read_text(encoding="utf-8"))
    applicability = None
    if not args.skip_applicability:
        applicability = evaluate_applicability(
            structured,
            profile,
            model=args.model,
            cache_dir=args.llm_cache_dir,
        )
        applicability_output = (
            Path(args.applicability_output)
            if args.applicability_output
            else ensure_dir(structured_path.parent) / "09_applicability.json"
        )
        write_json(applicability_output, applicability.model_dump(mode="json"))
    if not args.skip_llm_report:
        report = generate_narrative_report(
            structured,
            profile,
            applicability=applicability,
            model=args.model,
            cache_dir=args.llm_cache_dir,
        )
        report_output = (
            Path(args.llm_report_output)
            if args.llm_report_output
            else ensure_dir(structured_path.parent) / "10_llm_report.md"
        )
        report_output.parent.mkdir(parents=True, exist_ok=True)
        report_output.write_text(report.report_markdown, encoding="utf-8")
    print(
        json.dumps(
            {
                "applicability_output": str(args.applicability_output or structured_path.parent / "09_applicability.json"),
                "llm_report_output": str(args.llm_report_output or structured_path.parent / "10_llm_report.md"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
