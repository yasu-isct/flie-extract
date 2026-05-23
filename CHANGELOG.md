# Changelog

## 0.5.0 - Category-specific extraction schemas

### Added

- Added category-specific Pydantic extraction schemas:
  - `PeriodExtraction`
  - `MethodExtraction`
  - `DocumentExtraction`
  - `ExamExtraction`
  - `FeeExtraction`
  - `EnglishExtraction`
- Added `parse_chunk_by_category` to route each chunk to the smallest relevant response schema.
- Added tests for category response-model routing and conversion back to `AdmissionInfo`.

### Improvement

- Profile pipeline now uses category-specific small schemas instead of always requesting the full `AdmissionInfo` schema.
- This should reduce output size, noisy empty fields, and LLM latency for profile-driven parsing.
- The final merged output remains compatible with the existing report generator because focused results are converted back into `AdmissionInfo`.

### Known Issues

- General chunks still use the full `AdmissionInfo` schema.
- The next optimization should add a pre-pass to drop low-value general chunks or summarize them before extraction.

## 0.4.0 - Category-routed profile extraction

### Added

- Added `admission_parser.category_router` to classify selected chunks before LLM extraction.
- Added category-specific focus instructions for:
  - `documents`
  - `english`
  - `exams`
  - `fees`
  - `methods`
  - `periods`
  - `general`
- Added category counts to `profile_pipeline --dry-run` output.
- Added tests for category routing.

### Improvement

- Profile pipeline now sends a focused extraction instruction to the LLM for each selected chunk.
- This reduces unnecessary full-schema extraction behavior and should lower noisy warnings and output bloat.
- In the sample profile dry-run, 64 selected chunks were categorized as:
  - documents: 8
  - english: 11
  - exams: 14
  - fees: 9
  - general: 13
  - methods: 2
  - periods: 7

### Known Issues

- The model still returns the top-level `AdmissionInfo` schema for compatibility, even when instructed to focus on one category.
- A future optimization should use category-specific small schemas to further reduce output size and latency.

## 0.3.0 - Profile-driven chunk filtering

### Added

- Added `admission_parser.profile_filter` for applicant-profile based chunk filtering before LLM calls.
- Added `admission_parser.profile_pipeline` to parse PDFs with user profile inputs:
  - `--target`
  - `--english-test`
  - `--background`
  - `--dry-run`
- Added dry-run mode to inspect how many chunks would be sent to the LLM before spending API tokens.
- Added tests for profile chunk filtering.

### Improvement

- The pipeline can now filter chunks before LLM extraction instead of parsing the whole relevant-page set first.
- Example profile:
  - `情報理工学院`
  - `数理・計算科学系`
  - `情報工学系`
  - TOEFL
  - China mainland undergraduate background
- In the sample PDF dry-run, chunks were reduced from 123 to 64 before LLM calls.

### Known Issues

- Filtering is still rule-based and keyword-based.
- General chunks such as application periods and submission methods are intentionally retained, so some non-personal noise may remain.
- Department-specific extraction will be more accurate after the schema is extended with explicit target program fields.

## 0.2.0 - Personalized report MVP

### Added

- Added DeepSeek OpenAI-compatible API support through `OPENAI_BASE_URL`.
- Added `INSTRUCTOR_MODE=JSON` support for DeepSeek-compatible structured extraction.
- Added automatic model routing:
  - Flash model for normal extraction.
  - Pro model for long or multi-condition chunks.
- Added configurable model settings in `.env.example`:
  - `OPENAI_MODEL`
  - `OPENAI_PRO_MODEL`
  - `OPENAI_PRO_REASONING_ENABLED`
  - `OPENAI_PRO_THINKING_ENABLED`
  - `LLM_USE_PRO_FOR_COMPLEX`
  - `LLM_PRO_COMPLEX_CHAR_THRESHOLD`
- Added `admission_parser.reporter` to generate human-readable Markdown reports from parsed JSON.
- Added applicant profile filtering for reports:
  - target college / department / program keywords via `--target`
  - English test type via `--english-test`
  - applicant background via `--background`
- Added `.idea/` to `.gitignore`.

### Fixed

- Fixed DeepSeek API compatibility issue where Instructor's default tool-calling mode caused:
  - `Thinking mode does not support this tool_choice`
- Fixed Windows console `UnicodeEncodeError` when `pipeline.py` printed Japanese warnings to a GBK console.
- Fixed overly aggressive Pro routing that sent short keyword chunks to `deepseek-v4-pro`, causing the full parse to run too slowly.
- Restored `.env.example` after it was accidentally removed locally.

### Generated Artifacts

- `outputs/2027_4_2026_9_master.json`
  - First full structured JSON output from the sample PDF.
- `outputs/2027_4_2026_9_master_report.md`
  - General readable report.
- `outputs/2027_4_2026_9_master_personal_report.md`
  - Applicant-profile filtered report for:
    - `情報理工学院`
    - `数理・計算科学系`
    - `情報工学系`
    - TOEFL
    - China mainland undergraduate background

These generated artifacts remain ignored by Git through `outputs/`.

### Known Issues

- The current JSON schema does not yet attach every extracted item to a precise college / department / program.
- Applicant-profile filtering is currently rule-based and keyword-based, so it may keep some general information or miss items that are implicitly tied to a department.
- Some extracted dates remain `null` when the source chunk omits the year or when the model does not infer it safely.
- The JSON output is still a machine-readable intermediate artifact; the Markdown report should be treated as the human-facing output.
- Source page numbers are incomplete for some extracted items because not every chunk retained page metadata cleanly.

### Next Steps

- Extend schema fields with:
  - `target_college`
  - `target_department`
  - `target_program`
  - `applicable_background`
  - `applicable_english_test`
- Improve chunk page metadata preservation.
- Add tests for `reporter.py` profile filtering.
- Add a checklist-style report mode for applicant task tracking.
