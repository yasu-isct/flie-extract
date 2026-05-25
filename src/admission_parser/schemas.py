from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class SubmissionMode(str, Enum):
    online = "オンライン"
    postal = "郵送"
    in_person = "持参"
    other = "その他"
    unknown = "不明"


class DeadlineRule(str, Enum):
    must_arrive = "必着"
    postmark_valid = "消印有効"
    not_specified = "不明"


class UniversityInfo(BaseModel):
    university_name: str = Field("", description="大学名")
    university_name_zh: str = Field("", description="大学名中文")
    graduate_school: str = Field("", description="研究科・専攻名")
    graduate_school_zh: str = Field("", description="研究科・専攻名中文")
    admission_year: int | None = Field(None, description="入試年度。西暦。")
    source_pdf: str = ""


class ApplicationPeriod(BaseModel):
    period_type: str = Field("", description="例: 出願期間, 書類提出期間")
    start_date: str | None = Field(None, description="YYYY-MM-DD")
    end_date: str | None = Field(None, description="YYYY-MM-DD")
    time: str = Field("", description="時刻、受付時間など")
    deadline_rule: DeadlineRule = DeadlineRule.not_specified
    notes: str = ""
    source_pages: list[int] = Field(default_factory=list)


class SubmissionMethod(BaseModel):
    mode: SubmissionMode = SubmissionMode.unknown
    details: str = ""
    destination: str = ""
    source_pages: list[int] = Field(default_factory=list)


class RequiredDocument(BaseModel):
    name: str = Field("", description="提出書類名")
    name_zh: str = Field("", description="提出書類名中文")
    copies: str = Field("", description="必要部数")
    has_form: bool | None = Field(None, description="所定様式の有無")
    destination: str = ""
    conditions: str = Field("", description="対象者条件、免除条件など")
    notes: str = ""
    source_pages: list[int] = Field(default_factory=list)


class ExamSchedule(BaseModel):
    exam_type: str = ""
    date: str | None = Field(None, description="YYYY-MM-DD")
    time: str = ""
    place: str = ""
    notes: str = ""
    source_pages: list[int] = Field(default_factory=list)


class FeeInfo(BaseModel):
    amount_yen: int | None = None
    payment_method: str = ""
    payment_period: str = ""
    notes: str = ""
    source_pages: list[int] = Field(default_factory=list)


class EnglishRequirement(BaseModel):
    test_type: str = Field("", description="TOEFL, TOEIC, IELTSなど")
    accepted_variants: list[str] = Field(default_factory=list, description="例: TOEFL iBT, TOEFL iBT Home Edition")
    rejected_variants: list[str] = Field(default_factory=list, description="例: TOEFL ITP, TOEIC IP")
    minimum_score: str = ""
    direct_delivery_required: bool | None = Field(None, description="直送要否")
    institution_code: str = Field("", description="ETS DI codeなど")
    applicable_to: str = Field("", description="対象専攻、対象者、適用条件")
    exceptions: list[str] = Field(default_factory=list, description="例外条件")
    condition_logic: Literal["AND", "OR", "UNKNOWN"] = "UNKNOWN"
    notes: str = ""
    source_pages: list[int] = Field(default_factory=list)


class ExtractionWarning(BaseModel):
    field: str = Field("", description="Affected field, such as fees or exam_schedules")
    message: str = Field("", description="Chinese warning message")
    category: str = Field("", description="Chunk category or warning category")
    severity: Literal["info", "warning", "error"] = "warning"
    source_pages: list[int] = Field(default_factory=list)


class AdmissionInfo(BaseModel):
    university: UniversityInfo = Field(default_factory=UniversityInfo)
    application_periods: list[ApplicationPeriod] = Field(default_factory=list)
    submission_methods: list[SubmissionMethod] = Field(default_factory=list)
    required_documents: list[RequiredDocument] = Field(default_factory=list)
    exam_schedules: list[ExamSchedule] = Field(default_factory=list)
    fees: list[FeeInfo] = Field(default_factory=list)
    english_requirements: list[EnglishRequirement] = Field(default_factory=list)
    global_submission_rules: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    structured_warnings: list[ExtractionWarning] = Field(default_factory=list)

    @field_validator("global_submission_rules")
    @classmethod
    def strip_rules(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value and value.strip()]


class PeriodExtraction(BaseModel):
    application_periods: list[ApplicationPeriod] = Field(default_factory=list)
    global_submission_rules: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    structured_warnings: list[ExtractionWarning] = Field(default_factory=list)


class MethodExtraction(BaseModel):
    submission_methods: list[SubmissionMethod] = Field(default_factory=list)
    global_submission_rules: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    structured_warnings: list[ExtractionWarning] = Field(default_factory=list)


class DocumentExtraction(BaseModel):
    required_documents: list[RequiredDocument] = Field(default_factory=list)
    global_submission_rules: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    structured_warnings: list[ExtractionWarning] = Field(default_factory=list)


class ExamExtraction(BaseModel):
    exam_schedules: list[ExamSchedule] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    structured_warnings: list[ExtractionWarning] = Field(default_factory=list)


class FeeExtraction(BaseModel):
    fees: list[FeeInfo] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    structured_warnings: list[ExtractionWarning] = Field(default_factory=list)


class EnglishExtraction(BaseModel):
    english_requirements: list[EnglishRequirement] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    structured_warnings: list[ExtractionWarning] = Field(default_factory=list)
