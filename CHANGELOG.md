# Changelog

## 0.8.0 - Hybrid cursor and local vector retrieval

### Added

- Added `vector_retriever.py` for local n-gram chunk retrieval.
  - Uses character 2-4 grams, word tokens, and cosine similarity.
  - Requires no embedding API, no network call, and no new dependency.
- Added profile-pipeline retrieval controls:
  - `--page-scope relevant|all`
  - `--retrieval-mode none|vector|hybrid`
  - `--top-k`
  - `--run-dir`
- Added numbered run artifacts under `--run-dir`:
  - `01_page_profile_summary.json`
  - `02_clean.md`
  - `03_chunks.json`
  - `04_cursor_chunks.json`
  - `04_cursor_decisions.json`
  - `05_retrieved_chunks.json`
  - `05_retrieval_decisions.json`
  - `06_dry_run_summary.json` or `06_structured.json`
  - `07_report.md`
- Added `_user_requirements` enrichment for applicant-specific summaries, action items, and manual-confirmation points.
- Added tests for user requirement enrichment, n-gram retrieval, and hybrid profile-pipeline selection.

### Improved

- The recommended extraction framework is now cursor + vector hybrid selection:
  - cursor selection keeps profile-specific deterministic recall;
  - local vector retrieval supplements chunks missed by keyword/cursor rules;
  - category quotas reduce over-selection before LLM calls.
- `profile_pipeline.py` can now run from all PDF pages instead of depending only on keyword-based relevant pages.
- `reporter.py` renders user requirement summaries into the final Markdown report.

### Fixed

- Fixed an `EnglishRequirement.condition_logic` merge bug where combining different chunks could produce invalid values such as `UNKNOWN / AND`.

### Observed Effect

- Pure local n-gram retrieval dry-run on `2027_4_2026_9_master.pdf`:
  - source chunks: `291`
  - cursor chunks: `102`
  - selected vector chunks: `30`
- Pure vector API run completed in about `407.4` seconds, but report quality regressed because `top-k=30` over-compressed the context and introduced some unrelated chunks.
- Hybrid dry-run on the same sample:
  - source chunks: `291`
  - cursor chunks: `102`
  - selected hybrid chunks: `52`
  - category counts:
    - documents: `9`
    - english: `8`
    - exams: `12`
    - fees: `6`
    - general: `10`
    - methods: `4`
    - periods: `3`

### Notes

- The keyword-based `*_relevant_pages.json` layer is now treated as a diagnostic and optional prefilter, not the only retrieval strategy.
- The next optimization target is to tune hybrid category quotas and exclusion rules so unrelated schools/programs are filtered more aggressively.
- Validation after this update: `26 passed`.

## 0.7.0 - Profile cursor input and selection

### Added

- Added `profile_input.py` for optional applicant-profile input through:
  - CLI arguments
  - YAML/JSON config files
  - interactive prompts
- Added `cursor_selector.py` to convert applicant profiles into extraction cursors.
- Added `configs/applicant_profile.example.yaml` as a reproducible profile template.
- Added cursor diagnostics:
  - `*_cursor_chunks.json`
  - `*_cursor_decisions.json`
- Added tests for profile input merging and cursor-based chunk selection.

### Improved

- Profile pipeline now uses profile-guided cursor selection before LLM extraction.
- New cursor fields include:
  - target college
  - target department
  - target program
  - degree level
  - exam type
  - English test
  - applicant background
  - nationality / region
  - strict mode
- Default output paths are now organized into:
  - `outputs/final_reports/`
  - `outputs/final_json/`
  - `outputs/intermediate/`
  - `outputs/diagnostics/`
  - `outputs/smoke_tests/`

### Observed Effect

- On `2027_4_2026_9_master.pdf`, dry-run chunk selection changed from:
  - source chunks: `123`
  - previous profile filter selected chunks: `64`
  - new cursor-selected chunks: `51`

### Notes

- This is an input-side token compression step. It has not yet been validated with a full LLM re-run for field accuracy and omission rate.
- The old `--target` argument remains available for compatibility, but new experiments should prefer explicit cursor fields such as `--target-college`, `--target-department`, `--degree-level`, and `--exam-type`.

## 0.6.0 - Output quality cleanup

### Added

- Added structured warning schema:
  - `ExtractionWarning`
  - `AdmissionInfo.structured_warnings`
- Added extended English requirement fields:
  - `accepted_variants`
  - `rejected_variants`
  - `institution_code`
  - `applicable_to`
  - `exceptions`
- Added fuzzy merge tests for repeated periods, duplicate documents, English variants, and warning structuring.

### Improved

- Strengthened LLM prompts to prevent English fallback warnings.
- Category focus instructions now explicitly require Chinese warnings and empty lists when focused information is absent.
- Added fuzzy deduplication in `merger.py` for:
  - application periods
  - required documents
  - submission methods
  - exam schedules
  - fees
  - English requirements
- Reports now display structured English-test details such as accepted variants, rejected variants, institution code, target scope, and exceptions.

### Fixed

- Reduced duplicate application-period rows caused by repeated PDF content across pages/chunks.
- Preserved distinct English variants such as `TOEFL iBT` and `TOEFL iBT Home Edition` instead of collapsing them as duplicates.
- Converted validator-generated warning strings into structured warnings as well as legacy warning strings.

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
