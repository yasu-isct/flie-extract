# 2026-05-25 Experiment Notes

## Context

Sample PDF:

- `samples/2027_4_2026_9_master.pdf`
- 85 pages
- Text extraction was available through both PyMuPDF and pdfplumber.

Primary user profile used during optimization:

- Target: `情報理工学院`
- Target: `数理・計算科学系`
- Target: `情報工学系`
- English test: TOEFL
- Background: China mainland undergraduate (`cn_undergrad`)

## Baseline Artifacts

Backed up locally to:

```text
backups/2026-05-25_pre_profile_optimized_run/
```

Important baseline outputs:

```text
outputs/2027_4_2026_9_master.json
outputs/2027_4_2026_9_master_report.md
outputs/2027_4_2026_9_master_personal_report.md
outputs/2027_4_2026_9_master_relevant_pages.json
outputs/2027_4_2026_9_master_relevant_clean.md
outputs/2027_4_2026_9_master_relevant_chunks.json
outputs/profile_dry_run.json
outputs/profile_dry_run_profile_chunks.json
outputs/profile_dry_run_profile_chunk_decisions.json
```

## Previous Runtime Notes

These times were observed from command execution logs:

| Step | Result | Runtime |
| --- | --- | ---: |
| PDF environment test | 85 pages detected | about 3.2s |
| Profiler + full clean extraction | relevant pages detected and full clean MD generated | about 32s |
| Relevant-page clean extraction | `relevant_clean.md` generated | about 5.4s |
| First full pipeline attempt | timed out before completion | 1804s |
| Second full pipeline attempt | JSON generated, then Windows console print failed on Unicode | 1945s |
| Pro smoke chunk | `smoke_chunk_auto.json` generated | about 62s |
| Flash smoke chunk | `smoke_chunk_0.json` generated | about 13s |
| Profile dry-run before small-schema routing | 123 chunks to 64 selected chunks | about 25-28s |

## Baseline Structured JSON Summary

File:

```text
outputs/2027_4_2026_9_master.json
```

Observed counts:

| Field | Count |
| --- | ---: |
| application_periods | 10 |
| submission_methods | 11 |
| required_documents | 48 |
| exam_schedules | 20 |
| fees | 7 |
| english_requirements | 4 |
| warnings | 82 |

Main issue:

- The JSON is useful as a machine-readable intermediate artifact, but too noisy for direct human use.
- Repeated low-value notes such as "確認すること" and "詳細参照" made the output hard to read.
- Many extracted items were not bound to a specific target college / department / program.

## Optimization Timeline

### 0.2.0 DeepSeek + Report Generation

Commit:

```text
bb77fd7 Add DeepSeek support and personalized reports
```

Changes:

- Added `OPENAI_BASE_URL` support for DeepSeek.
- Switched Instructor to JSON mode for DeepSeek compatibility.
- Added Flash / Pro routing.
- Added Markdown report generation.
- Added applicant profile filtering in reports.

Bug fixes:

- Fixed DeepSeek `Thinking mode does not support this tool_choice`.
- Fixed Windows `UnicodeEncodeError` in `pipeline.py` console output.
- Reduced overly aggressive Pro routing.

### 0.3.0 Profile-driven Chunk Filtering

Commit:

```text
f56fb2f Add profile-driven chunk filtering
```

Changes:

- Added `profile_filter.py`.
- Added `profile_pipeline.py`.
- Added `--target`, `--english-test`, `--background`, and `--dry-run`.
- Moved filtering before LLM calls.

Observed effect:

- Source chunks: 123
- Selected chunks: 64

### 0.4.0 Category-routed Profile Extraction

Commit:

```text
7ab7dbc Add category-routed profile extraction
```

Changes:

- Added `category_router.py`.
- Classified selected chunks into:
  - documents
  - english
  - exams
  - fees
  - general
  - methods
  - periods
- Added category-specific focus instructions.

Dry-run category counts:

| Category | Count |
| --- | ---: |
| documents | 8 |
| english | 11 |
| exams | 14 |
| fees | 9 |
| general | 13 |
| methods | 2 |
| periods | 7 |

### 0.5.0 Category-specific Small Schemas

Commit:

```text
4c841c0 Add category-specific extraction schemas
```

Changes:

- Added small Pydantic schemas:
  - `PeriodExtraction`
  - `MethodExtraction`
  - `DocumentExtraction`
  - `ExamExtraction`
  - `FeeExtraction`
  - `EnglishExtraction`
- Added `parse_chunk_by_category`.
- Profile pipeline now sends chunks to category-specific response schemas.

Expected benefit:

- Less output bloat.
- Fewer empty fields.
- Fewer noisy warnings.
- Lower latency per chunk compared with asking for the full `AdmissionInfo` schema every time.

## Current Recommended Run

Dry-run first:

```powershell
.\.venv\Scripts\python.exe -m admission_parser.profile_pipeline samples\2027_4_2026_9_master.pdf `
  --target 情報理工学院 `
  --target 数理・計算科学系 `
  --target 情報工学系 `
  --english-test toefl `
  --background cn_undergrad `
  --dry-run `
  --output outputs\profile_dry_run.json
```

Full optimized profile run:

```powershell
.\.venv\Scripts\python.exe -m admission_parser.profile_pipeline samples\2027_4_2026_9_master.pdf `
  --target 情報理工学院 `
  --target 数理・計算科学系 `
  --target 情報工学系 `
  --english-test toefl `
  --background cn_undergrad `
  --output outputs\2027_4_2026_9_master_profile_optimized.json `
  --report-output outputs\2027_4_2026_9_master_profile_optimized_report.md
```

## Optimized Profile Run Result

Run date:

```text
2026-05-25
```

Command:

```powershell
.\.venv\Scripts\python.exe -m admission_parser.profile_pipeline samples\2027_4_2026_9_master.pdf `
  --target 情報理工学院 `
  --target 数理・計算科学系 `
  --target 情報工学系 `
  --english-test toefl `
  --background cn_undergrad `
  --output outputs\2027_4_2026_9_master_profile_optimized.json `
  --report-output outputs\2027_4_2026_9_master_profile_optimized_report.md
```

Runtime:

```text
571.91s
```

Output files:

```text
outputs/2027_4_2026_9_master_profile_optimized.json
outputs/2027_4_2026_9_master_profile_optimized_report.md
```

Optimized output summary:

| Field | Count |
| --- | ---: |
| application_periods | 2 |
| submission_methods | 3 |
| required_documents | 28 |
| exam_schedules | 20 |
| fees | 9 |
| english_requirements | 10 |
| warnings | 11 |

Profile routing summary:

| Metric | Count |
| --- | ---: |
| source_chunks | 123 |
| selected_chunks | 64 |
| documents | 8 |
| english | 11 |
| exams | 14 |
| fees | 9 |
| general | 13 |
| methods | 2 |
| periods | 7 |

Comparison with previous full run:

| Metric | Previous full run | Optimized profile run |
| --- | ---: | ---: |
| runtime | 1945s | 571.91s |
| JSON size | 53,485 bytes | 29,507 bytes |
| report size | 17,064 bytes | 7,081 bytes |
| warnings | 82 | 11 |

Observed improvement:

- Runtime reduced by about 70.6%.
- JSON size reduced by about 44.8%.
- Warning count reduced by about 86.6%.
- Output is now profile-specific rather than full-document oriented.

## Rollback Reference

Known commits:

```text
c4b2285 Initial admission parser MVP
bb77fd7 Add DeepSeek support and personalized reports
f56fb2f Add profile-driven chunk filtering
7ab7dbc Add category-routed profile extraction
4c841c0 Add category-specific extraction schemas
```

If the latest small-schema optimization has problems, revert to:

```text
7ab7dbc
```

For normal collaborative workflows, prefer `git revert` instead of rewriting history.

## 2026-06-04 Profile Cursor Input Update

New modules:

```text
src/admission_parser/profile_input.py
src/admission_parser/cursor_selector.py
configs/applicant_profile.example.yaml
```

Purpose:

- Move from broad keyword filtering to profile-guided cursor selection.
- Let the user provide optional detailed applicant information before each run.
- Convert that profile into positive keywords, negative keywords, global-section rules, and target anchors before LLM calls.

Supported input styles:

```powershell
.\.venv\Scripts\python.exe -m admission_parser.profile_pipeline samples\2027_4_2026_9_master.pdf `
  --profile-config configs\applicant_profile.example.yaml `
  --dry-run
```

or explicit CLI cursor fields:

```powershell
.\.venv\Scripts\python.exe -m admission_parser.profile_pipeline samples\2027_4_2026_9_master.pdf `
  --target-college 情報理工学院 `
  --target-department 数理・計算科学系 `
  --target-department 情報工学系 `
  --degree-level master `
  --exam-type general `
  --english-test toefl `
  --background cn_undergrad `
  --nationality-or-region china `
  --dry-run
```

Dry-run result on the current sample:

| Metric | Count |
| --- | ---: |
| source_chunks | 123 |
| previous profile-filter selected_chunks | 64 |
| new cursor-selected chunks | 51 |

New cursor category counts:

| Category | Count |
| --- | ---: |
| documents | 4 |
| english | 7 |
| exams | 10 |
| fees | 7 |
| general | 19 |
| methods | 2 |
| periods | 6 |

Generated diagnostics:

```text
outputs/diagnostics/2027_4_2026_9_master_profile_dry_run.json
outputs/diagnostics/2027_4_2026_9_master_profile_dry_run_cursor_chunks.json
outputs/diagnostics/2027_4_2026_9_master_profile_dry_run_cursor_decisions.json
```

Interpretation:

- The new cursor layer reduced selected chunks by about 20.3% compared with the previous profile filter (`64 -> 51`).
- Compared with the original relevant-page chunk set, selected chunks decreased by about 58.5% (`123 -> 51`).
- This is an input-side token compression result only; the next step is to run the LLM and compare field accuracy, omission rate, runtime, and warnings.
