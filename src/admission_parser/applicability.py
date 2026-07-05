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
BASE_FACTS_PROMPT_VERSION = "base_facts_v1"

DOCUMENT_FACT_KEYS = (
    "university",
    "application_periods",
    "submission_methods",
    "required_documents",
    "exam_schedules",
    "fees",
    "english_requirements",
    "global_submission_rules",
    "warnings",
    "structured_warnings",
)

RUNTIME_METADATA_KEYS = {
    "_artifacts",
    "llm_cache_dir",
    "llm_cache_hits",
    "llm_cache_misses",
}

RUNTIME_METADATA_PREFIXES = (
    "elapsed_",
    "runtime_",
)


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


class BaseFact(BaseModel):
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
    summary: str = Field("", description="Profile-independent Chinese summary of this fact.")
    source_pages: list[int] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class BaseFactsResult(BaseModel):
    document_summary: str = ""
    facts: list[BaseFact] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)


APPLICABILITY_SYSTEM_PROMPT = """
你是日本大学院募集要项的适用性判定专家。你会收到已经结构化抽取后的 JSON 和申请者画像。
你的任务不是重新抽取 PDF，而是判断已有条目是否适用于该申请者。
必须只使用输入 JSON 中存在的信息；不要编造日期、金额、条件、系名或材料。
如果输入里包含 base facts，请优先复用这些不依赖申请者画像的文档事实，再结合申请者画像做适用性判断。
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

BASE_FACTS_SYSTEM_PROMPT = """
你是日本大学院募集要项的文档事实整理助手。
你会收到已经结构化抽取后的 JSON。你的任务是生成不依赖任何申请者画像的 base facts。
请只整理输入 JSON 中明确存在的信息，不要判断某个具体申请者是否适用。
重点保留：申请时间、提交方式、必要材料、考试日程、费用、英语考试规则、警告和不确定点。
如果日语条件表达需要解释，例如「数学系を除く全系」「該当者のみ」「又は」，可以用中文解释其一般含义，但不要绑定到具体用户。
每个事实尽量保留 source_pages 和短 evidence。
输出必须是中文；证据片段可以保留原文日文。
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


def _is_runtime_metadata_key(key: str) -> bool:
    return key in RUNTIME_METADATA_KEYS or key.startswith(RUNTIME_METADATA_PREFIXES)


def stable_payload(payload: Any) -> Any:
    """Return the semantic payload used for applicability/report prompts and cache keys."""
    if isinstance(payload, dict):
        return {
            key: stable_payload(value)
            for key, value in payload.items()
            if not _is_runtime_metadata_key(str(key))
        }
    if isinstance(payload, list):
        return [stable_payload(item) for item in payload]
    return payload


def document_facts_payload(structured: dict[str, Any]) -> dict[str, Any]:
    """Return profile-independent structured facts from a pipeline payload."""
    stable = stable_payload(structured)
    if not isinstance(stable, dict):
        return {}
    return {key: stable[key] for key in DOCUMENT_FACT_KEYS if key in stable}


def _cache_key(kind: str, prompt_version: str, model: str, payload: dict[str, Any]) -> str:
    raw = _compact_json(
        {
            "kind": kind,
            "prompt_version": prompt_version,
            "model": model,
            "payload": stable_payload(payload),
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


def _base_facts_payload(base_facts: BaseFactsResult | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(base_facts, BaseFactsResult):
        return base_facts.model_dump(mode="json")
    if isinstance(base_facts, dict):
        return stable_payload(base_facts)
    return {}


def generate_base_facts(
    structured: dict[str, Any],
    model: str | None = None,
    cache_dir: str | Path | None = Path("outputs") / "llm_cache",
) -> BaseFactsResult:
    selected_model = _model(model)
    facts_payload = document_facts_payload(structured)
    payload = {
        "structured": facts_payload,
    }
    key = _cache_key("base_facts", BASE_FACTS_PROMPT_VERSION, selected_model, payload)
    cached = _load_cache(cache_dir, key, BaseFactsResult)
    if cached is not None:
        return cached

    user_prompt = (
        "请基于以下结构化募集要项 JSON，生成不依赖申请者画像的 base facts。\n\n"
        f"结构化 JSON:\n{json.dumps(facts_payload, ensure_ascii=False, indent=2)}"
    )
    result = _client().chat.completions.create(
        model=selected_model,
        response_model=BaseFactsResult,
        messages=[
            {"role": "system", "content": BASE_FACTS_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        max_retries=2,
    )
    _write_cache(cache_dir, key, result, "base_facts", BASE_FACTS_PROMPT_VERSION, selected_model)
    return result


def evaluate_applicability(
    structured: dict[str, Any],
    profile: ApplicantProfileV2,
    base_facts: BaseFactsResult | dict[str, Any] | None = None,
    model: str | None = None,
    cache_dir: str | Path | None = Path("outputs") / "llm_cache",
) -> ApplicabilityResult:
    selected_model = _model(model)
    stable_structured = document_facts_payload(structured)
    stable_base_facts = _base_facts_payload(base_facts)
    payload = {
        "profile": _profile_payload(profile),
        "structured": stable_structured,
        "base_facts": stable_base_facts,
    }
    key = _cache_key("applicability", APPLICABILITY_PROMPT_VERSION, selected_model, payload)
    cached = _load_cache(cache_dir, key, ApplicabilityResult)
    if cached is not None:
        return cached

    user_prompt = (
        "请基于以下申请者画像和结构化募集要项 JSON，判断各条目是否适用于该申请者。\n\n"
        f"申请者画像:\n{json.dumps(_profile_payload(profile), ensure_ascii=False, indent=2)}\n\n"
        f"Base facts:\n{json.dumps(stable_base_facts, ensure_ascii=False, indent=2)}\n\n"
        f"结构化 JSON:\n{json.dumps(stable_structured, ensure_ascii=False, indent=2)}"
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
    base_facts: BaseFactsResult | dict[str, Any] | None = None,
    model: str | None = None,
    cache_dir: str | Path | None = Path("outputs") / "llm_cache",
) -> NarrativeReportResult:
    selected_model = _model(model)
    applicability_payload = (
        applicability.model_dump(mode="json")
        if isinstance(applicability, ApplicabilityResult)
        else applicability
    )
    stable_structured = document_facts_payload(structured)
    stable_applicability = stable_payload(applicability_payload or {})
    stable_base_facts = _base_facts_payload(base_facts)
    payload = {
        "profile": _profile_payload(profile),
        "structured": stable_structured,
        "base_facts": stable_base_facts,
        "applicability": stable_applicability,
    }
    key = _cache_key("narrative_report", NARRATIVE_REPORT_PROMPT_VERSION, selected_model, payload)
    cached = _load_cache(cache_dir, key, NarrativeReportResult)
    if cached is not None:
        return cached

    user_prompt = (
        "请基于以下数据生成自然语言 Markdown 报告。\n\n"
        f"申请者画像:\n{json.dumps(_profile_payload(profile), ensure_ascii=False, indent=2)}\n\n"
        f"Base facts:\n{json.dumps(stable_base_facts, ensure_ascii=False, indent=2)}\n\n"
        f"结构化 JSON:\n{json.dumps(stable_structured, ensure_ascii=False, indent=2)}\n\n"
        f"适用性判定 JSON:\n{json.dumps(stable_applicability, ensure_ascii=False, indent=2)}"
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
    parser.add_argument("--skip-base-facts", action="store_true")
    parser.add_argument("--skip-llm-report", action="store_true")
    parser.add_argument("--llm-cache-dir", default=str(Path("outputs") / "llm_cache"))
    parser.add_argument("--model", default=None)
    add_profile_arguments(parser)
    args = parser.parse_args()

    profile = profile_from_args(args)
    structured_path = Path(args.structured_json)
    structured = json.loads(structured_path.read_text(encoding="utf-8"))
    base_facts = None
    if not args.skip_base_facts and (not args.skip_applicability or not args.skip_llm_report):
        base_facts = generate_base_facts(
            structured,
            model=args.model,
            cache_dir=args.llm_cache_dir,
        )
    applicability = None
    if not args.skip_applicability:
        applicability = evaluate_applicability(
            structured,
            profile,
            base_facts=base_facts,
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
            base_facts=base_facts,
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
