# Profile-Guided Long Document Extractor

## English

This project explores **profile-guided cursor extraction for complex long documents**.  
Instead of sending an entire PDF to an LLM, it first builds a user/profile-specific extraction cursor, narrows the document into high-value chunks, and then applies category-specific structured schemas to generate reliable JSON and human-readable reports.

It is designed as a reusable extraction framework for administrative PDFs, policy documents, application manuals, and other long documents where small or local LLMs struggle with cost, context length, and noisy extraction.

Current recommended mode:

```powershell
.\.venv\Scripts\python.exe -m admission_parser.profile_pipeline samples\2027_4_2026_9_master.pdf `
  --profile-config configs\applicant_profile.example.yaml `
  --page-scope all `
  --retrieval-mode hybrid `
  --top-k 30 `
  --run-dir outputs\runs\2027_master_hybrid_run
```

The hybrid mode combines deterministic profile/cursor selection with local n-gram retrieval. It is designed to reduce keyword-only recall risk while keeping LLM input smaller than a full-document extraction.

## 日本語

本プロジェクトは、**複雑な長文書に対するプロファイル誘導型カーソル抽出**を扱う情報抽出システムです。  
PDF 全体をそのまま LLM に渡すのではなく、ユーザー条件に基づいて抽出カーソルを構築し、必要なチャンクだけに入力を圧縮したうえで、カテゴリ別の構造化 Schema により JSON と読みやすいレポートを生成します。

行政文書、申請要項、規程類などの長文 PDF を、小規模モデルやローカルモデルでも扱いやすい形へ変換するための汎用的な抽出フレームワークとして設計しています。

## 中文说明

本项目是一个面向复杂长文档的 profile-guided cursor extraction 框架：先根据用户条件构建抽取游标，在 LLM 调用前压缩输入范围，再通过结构化 Schema 输出 JSON 和可读报告。

它的目标是成为一个可泛化的长文档信息抽取工具，适用于行政 PDF、申请手册、政策文档、规程说明等高密度文本场景，尤其关注如何降低 token 消耗并提升小模型/本地模型的可用性。

## GitHub Description

English:

```text
Profile-guided cursor extraction for complex long PDFs: compresses LLM input and converts dense documents into structured JSON and readable reports.
```

日本語:

```text
プロファイル誘導型カーソル抽出により長文PDFのLLM入力を圧縮し、高密度文書を構造化JSONと可読レポートへ変換する汎用情報抽出プロジェクト。
```

## 当前状态

- PDF 解析：PyMuPDF + pdfplumber 双通道提取文本、block、word 和表格。
- 相关页筛选：根据可配置关键词和文档结构信号筛出目标页。
- 文本清洗：将相关页整理为 Markdown，表格转为 Markdown 表格。
- 切片：按日文标题和长度切成带页码、标题、PDF 名的 chunks。
- 画像输入：支持 CLI、YAML 配置和交互式输入。
- 游标筛选：根据目标实体、任务类型、用户条件和背景信息筛掉低价值 chunks。
- LLM 抽取：按类别调用更小的 Pydantic Schema，减少 token、输出噪声和等待时间。
- 后处理：合并多 chunk 结果，去重、校验日期、转换元号、结构化 warnings。
- 人类可读报告：从 JSON 生成申请者更容易阅读的 Markdown 报告。

## 项目结构

```text
.
├─ samples/                         # 本地 PDF 样本目录，PDF 默认不会上传到 Git
├─ outputs/                         # 运行结果目录，默认不上传到 Git
├─ backups/                         # 实验结果备份目录，默认不上传到 Git
├─ configs/
│  └─ universities.yaml             # 阶段二站点配置示例
├─ docs/
│  └─ experiments/                  # 实验记录、运行耗时、优化记录
├─ tests/                           # pytest 测试
├─ src/admission_parser/
│  ├─ profiler.py                   # 相关页筛选和页面结构探查
│  ├─ extractor.py                  # PyMuPDF + pdfplumber 文本/表格提取
│  ├─ chunker.py                    # Markdown 文本切片
│  ├─ profile_filter.py             # 按申请者画像筛选 chunks
│  ├─ profile_input.py              # 画像输入：CLI/YAML/交互式输入
│  ├─ cursor_selector.py            # 画像游标构建与 chunk 精选
│  ├─ category_router.py            # chunks 分类：材料、英语、考试、费用等
│  ├─ schemas.py                    # Pydantic 输出模型
│  ├─ llm_parser.py                 # Instructor + OpenAI-compatible LLM 调用
│  ├─ merger.py                     # 多 chunk 结果合并、去重、warnings 结构化
│  ├─ validator.py                  # 日期、必填字段、元号转换校验
│  ├─ reporter.py                   # JSON 转可读 Markdown 报告
│  ├─ pipeline.py                   # 通用完整解析主程序
│  ├─ profile_pipeline.py           # 推荐：画像驱动优化解析主程序
│  ├─ stage2/                       # 爬虫、更新检测、SQLite 持久化入口
│  └─ stage3/                       # diff、通知、定时任务入口
├─ .env.example                     # API 配置模板，可提交
├─ .env                             # 本地 API Key，禁止提交
├─ pyproject.toml                   # Python 项目配置
└─ test_env.py                      # PDF/LLM 环境验证脚本
```

## 快速开始

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .[dev]
```

把用于测试的长文档 PDF 放进 `samples/`。例如：

```text
samples/2027_4_2026_9_master.pdf
```

注意：`*.pdf` 已经写入 `.gitignore`，意思是 PDF 文件不会被 Git 跟踪，也不会被一起上传到 GitHub。这样可以避免误传大文件、版权文件或内部资料。

## API 配置

不要在 `.venv/` 里新建 API 配置文件。请在项目根目录创建 `.env`，位置如下：

```text
C:\Users\DELL\Documents\募集要项提取\.env
```

DeepSeek 示例：

```env
OPENAI_API_KEY=你的 DeepSeek API Key
OPENAI_BASE_URL=https://api.deepseek.com
INSTRUCTOR_MODE=JSON
OPENAI_MODEL=deepseek-v4-flash
OPENAI_PRO_MODEL=deepseek-v4-pro
OPENAI_PRO_REASONING_ENABLED=false
OPENAI_PRO_REASONING_EFFORT=high
OPENAI_PRO_THINKING_ENABLED=false
LLM_USE_PRO_FOR_COMPLEX=true
LLM_PRO_COMPLEX_CHAR_THRESHOLD=7000
```

`.env` 已经被 `.gitignore` 排除，不会上传到 GitHub。`.env.example` 是可以提交的模板，里面不能写真实 key。

## 基础验证

只验证 PDF 读取：

```powershell
.\.venv\Scripts\python.exe test_env.py samples\2027_4_2026_9_master.pdf
```

同时验证 LLM 连通性：

```powershell
.\.venv\Scripts\python.exe test_env.py samples\2027_4_2026_9_master.pdf --check-llm
```

## 推荐运行方式：画像驱动解析

推荐先使用画像配置文件。模板在：

```text
configs/applicant_profile.example.yaml
```

示例内容：

```yaml
target_college:
  - 情報理工学院
target_department:
  - 数理・計算科学系
  - 情報工学系
degree_level: master
exam_type: general
english_test: toefl
background: cn_undergrad
nationality_or_region: china
include_global_sections: true
strict_mode: false
```

先用 dry-run 看游标会筛出多少 chunks，不会调用 API，也不会花 token：

```powershell
.\.venv\Scripts\python.exe -m admission_parser.profile_pipeline samples\2027_4_2026_9_master.pdf `
  --profile-config configs\applicant_profile.example.yaml `
  --dry-run
```

确认筛选范围合理后，运行真正的 LLM 抽取：

```powershell
.\.venv\Scripts\python.exe -m admission_parser.profile_pipeline samples\2027_4_2026_9_master.pdf `
  --profile-config configs\applicant_profile.example.yaml `
  --output outputs\final_json\2027_4_2026_9_master_profile_optimized.json `
  --report-output outputs\final_reports\2027_4_2026_9_master_profile_optimized_report.md
```

也可以不用配置文件，直接通过 CLI 输入画像：

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

如果想逐项输入，可以使用：

```powershell
.\.venv\Scripts\python.exe -m admission_parser.profile_pipeline samples\2027_4_2026_9_master.pdf --interactive --dry-run
```

旧参数 `--target` 仍然兼容，但新实验建议优先使用 `--target-college`、`--target-department`、`--degree-level`、`--exam-type` 等更细的游标字段。

`--background` 可选值：

- `cn_undergrad`：中国大陆全日制本科
- `jp_undergrad`：日本本科
- `overseas_undergrad`：海外本科

## 通用完整解析

如果想不带画像，尽可能抽取整份文档的通用信息：

```powershell
.\.venv\Scripts\python.exe -m admission_parser.pipeline samples\2027_4_2026_9_master.pdf `
  --output outputs\final_json\2027_4_2026_9_master.json
```

这会比画像驱动版本更慢、更贵，也更容易保留对当前申请者无用的信息。

## 从已有 JSON 生成报告

```powershell
.\.venv\Scripts\python.exe -m admission_parser.reporter outputs\final_json\2027_4_2026_9_master_profile_optimized.json `
  --target 情報理工学院 `
  --target 数理・計算科学系 `
  --target 情報工学系 `
  --english-test toefl `
  --background cn_undergrad `
  --output outputs\final_reports\personal_report.md
```

## 输出文件说明

常见输出文件之间的关系如下：

```text
PDF
  ↓ profiler.py
*_relevant_pages.json       # 哪些页命中了关键词，以及每页的结构探查信息
  ↓ extractor.py
*_relevant_clean.md         # 相关页清洗后的 Markdown 文本，给人和 LLM 都能读
  ↓ chunker.py
*_relevant_chunks.json      # 带页码/标题/来源的切片，是 LLM 批量抽取的输入
  ↓ profile_input.py + cursor_selector.py
*_cursor_chunks.json        # 画像游标筛出的 LLM 输入
*_cursor_decisions.json     # 每个 chunk 被保留/丢弃的原因
  ↓ profile_pipeline.py + LLM + merger.py + validator.py
*_profile_optimized.json    # 最终结构化 JSON，适合程序读取
*_profile_optimized_report.md # 最终可读报告，适合人工查看
```

默认输出目录已经按用途分层：

- `outputs/final_reports/`：最终可读报告
- `outputs/final_json/`：最终结构化 JSON
- `outputs/intermediate/`：PDF 清洗、相关页、chunks 等过程文件
- `outputs/diagnostics/`：dry-run、chunk 选择决策等诊断文件
- `outputs/smoke_tests/`：小规模 API 测试结果

`*_relevant_pages.json` 不是最终结果，它的作用是解释“为什么这些页面被选中”。  
`*_relevant_chunks.json` 是把清洗后的 Markdown 拆成小块，方便模型逐块抽取，也方便后续做 token 压缩研究。  
`*_cursor_decisions.json` 是游标筛选日志，适合检查哪些 chunk 被保留、哪些被丢弃，以及原因是什么。  
真正建议查看的是 `*_profile_optimized_report.md`，JSON 更适合后端、看板和后续自动化使用。

## 已记录的优化结果

当前样本 `2027_4_2026_9_master.pdf` 的一次画像驱动优化运行结果记录在：

```text
docs/experiments/2026-05-25_run_baseline_and_optimizations.md
```

关键变化：

- LLM 处理 chunks：`123 -> 64`
- 运行时间：约 `1945s -> 571.91s`
- JSON 大小：约 `53,485 bytes -> 29,507 bytes`
- warnings：`82 -> 11`

这些数据说明当前优化方向已经明显降低了 API 时间和输出噪声，但还没有完成“本地 8B 模型也能稳定达到同等效果”的研究目标。

新增画像游标后，当前样本 dry-run 进一步将 chunks 从 `123` 压到 `51`。这个结果还需要用下一次 LLM 实跑确认字段遗漏率，但它已经可以作为 token 压缩实验的输入侧优化版本。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest
```

当前测试覆盖：

- chunker 切片
- profile_filter 画像过滤
- profile_input 画像输入
- cursor_selector 画像游标筛选
- category_router 分类路由
- llm_parser 分类 schema 路由
- merger 去重和 structured warnings
- validator 后处理校验

## Git 和 GitHub

常用命令：

```powershell
git status -sb
git add README.md
git commit -m "Update README"
git push
```

如果后续某次提交有问题，优先使用可审计的回滚方式：

```powershell
git log --oneline
git revert <commit_id>
git push
```

`git revert` 会生成一个新的“反向提交”，适合已经推送到 GitHub 的版本。除非非常确定，否则不要对已推送历史使用 `git reset --hard`。

## 后续研究方向

这个项目后续适合作为“长 PDF 行政文档的信息抽取与 token 压缩”研究原型。建议优先推进：

- 更细粒度的申请者画像字段：学院、系、专攻、入试区分、英语考试、学历背景、国籍/在留状态。
- chunk 压缩策略：标题树、关键词窗口、表格保真压缩、重复提示删除、跨页合并。
- 本地轻量模型对比：用 API 大模型结果做银标数据，再测试 8B 模型在压缩输入上的字段准确率。
- Docling 对比实验：把 Docling 作为第三解析后端或疑难页 fallback，与 PyMuPDF + pdfplumber 在表格保真、token 数、速度和抽取准确率上做 A/B/C 对比。
- 看板和纠错闭环：把人工修正数据沉淀为 few-shot 示例和错误模式报告。
