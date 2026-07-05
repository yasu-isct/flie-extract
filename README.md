# Profile-Guided Admission Document Intelligence

面向日本留学生申请场景的长文档解析原型。

本项目不是单次 PDF 总结工具，而是在探索一种更可落地的募集要项处理方式：把大学院募集要项从“很长、很难检索、很难复用的 PDF”，转成可追溯的证据、结构化事实、画像适用性判断和可读报告。

Current English summary:

> Profile-guided evidence selection and reasoning for long administrative PDFs. The pipeline compresses LLM input, keeps source evidence traceable, and generates structured JSON plus applicant-oriented reports.

## 当前定位

目标用户是准备申请日本大学院的学生，尤其是需要快速判断“我能不能报、要交什么、什么时候考、英语成绩是否适用”的场景。

当前样例是东京科学大学大学院募集要项，但项目主线不是写死单校规则，而是构建一个可泛化的 long document extractor：

- PDF 解析：PyMuPDF + pdfplumber 双通道提取文本、表格和页信息。
- 画像驱动：用申请者 profile 缩小候选范围，例如目标学院、目标系、学位、入试类型、英语考试、学历背景。
- 证据检索：cursor/profile selection + n-gram 或 local embedding retrieval。
- 引用扩展：识别“下記(1)”这类文档内跳转，并做 direct/recursive reference expansion。
- LLM 抽取：把 selected chunks 按 category 分组，合并成 batch，并行请求 API，返回结构化 JSON。
- 适用性判断：对抽取出的事实做 applicant-specific applicability pass。
- 可读报告：基于结构化事实和适用性判断生成面向申请者的 Markdown 报告。
- 缓存实验：已有 local embedding cache、LLM extraction cache、profile-independent base facts cache、applicability/report cache MVP。

更完整的产品主线见：

- [docs/product_mainline.md](docs/product_mainline.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/roadmap.md](docs/roadmap.md)

## 推荐主线

下一阶段推荐从单纯字段抽取，升级到 evidence + question + logic-chain extraction。

```text
PDF
 -> Evidence Index
 -> Question Plan
 -> Recursive Evidence Gathering
 -> Logic Chain Synthesis
 -> Applicability Pass
 -> Narrative Report
```

这个方向的核心是：本地代码负责解析、索引、检索、缓存和证据追踪；LLM 负责理解证据、生成结构化判断和自然语言报告。

## 当前能力状态

已经完成：

- PDF 文本/表格抽取。
- chunker、page boundary split、profile input。
- profile-guided cursor selector。
- hybrid retrieval。
- n-gram retrieval backend。
- local embedding retrieval backend，默认模型路径可使用 `models/bge-m3`。
- retrieval cross-check HTML/JSON/Markdown 诊断产物。
- category-batched parallel LLM extraction。
- LLM extraction cache。
- applicability pass。
- LLM narrative report。
- recursive reference expansion MVP。
- chunk 边界强化，降低跨页、跨学系污染。
- pytest 覆盖当前核心模块。

仍在优化：

- document-level manifest。
- 更稳定的 embedding index/cache 管理层。
- reasoning-chain MVP。
- report/applicability cache key 去除运行态字段。
- 主流大学募集要项的离线索引和复用。
- 面向本地小模型的蒸馏/LoRA 数据积累。

## 安装

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .[dev]
```

如果要使用本地向量检索：

```powershell
python -m pip install -e .[embedding]
```

或者一次安装：

```powershell
python -m pip install -e .[dev,embedding]
```

## 本地文件

这些文件和目录默认不上传 GitHub：

- `.env`
- `samples/`
- `models/`
- `outputs/`

建议放置：

```text
samples/2027_4_2026_9_master.pdf
models/bge-m3/
outputs/
```

`models/bge-m3` 体积较大，只保留在本地。

## API 配置

在项目根目录创建 `.env`，不要放进 `.venv/`。

示例：

```env
OPENAI_API_KEY=your_api_key
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

`.env.example` 可以提交，真实 `.env` 不要提交。

## 快速验证

```powershell
.\.venv\Scripts\python.exe -m pytest
```

当前基准：`37 passed`。

## 推荐 dry-run

dry-run 不调用 LLM，适合确认 chunk 筛选、retrieval 和 reference expansion 的效果。

```powershell
.\.venv\Scripts\python.exe -m admission_parser.profile_pipeline samples\2027_4_2026_9_master.pdf `
  --profile-config configs\applicant_profile.example.yaml `
  --dry-run `
  --page-scope all `
  --retrieval-mode hybrid `
  --retrieval-backend ngram `
  --retrieval-source cursor `
  --top-k 30 `
  --reference-expansion direct `
  --run-dir outputs\runs\2027_master_ngram_cursor_dry_run
```

## 本地 embedding dry-run

如果本地已经有 `models/bge-m3`：

```powershell
.\.venv\Scripts\python.exe -m admission_parser.profile_pipeline samples\2027_4_2026_9_master.pdf `
  --profile-config configs\applicant_profile.example.yaml `
  --dry-run `
  --page-scope all `
  --retrieval-mode hybrid `
  --retrieval-backend local-embedding `
  --retrieval-source cursor `
  --embedding-model-path models\bge-m3 `
  --embedding-cache-dir outputs\embedding_cache `
  --top-k 30 `
  --reference-expansion direct `
  --run-dir outputs\runs\2027_master_embedding_cursor_dry_run
```

注意：当前 embedding cache 还是“按输入文本集合 hash 的本地缓存”，不是完整 index 管理层。重复跑同一批输入会命中缓存，但 chunks、参数或文本集合变化时会生成新的缓存文件。

## 完整 LLM 运行

```powershell
.\.venv\Scripts\python.exe -m admission_parser.profile_pipeline samples\2027_4_2026_9_master.pdf `
  --profile-config configs\applicant_profile.example.yaml `
  --page-scope all `
  --retrieval-mode hybrid `
  --retrieval-backend local-embedding `
  --retrieval-source cursor `
  --embedding-model-path models\bge-m3 `
  --embedding-cache-dir outputs\embedding_cache `
  --top-k 30 `
  --reference-expansion direct `
  --llm-cache-dir outputs\llm_cache `
  --applicability-pass `
  --llm-report `
  --run-dir outputs\runs\2027_master_full_run
```

LLM 不是直接返回最终报告。当前流程是：

```text
selected chunks
 -> category-batched API requests
 -> structured JSON
 -> local merge / validate
 -> applicability pass
 -> narrative report
```

## 常见输出

使用 `--run-dir` 时，主要产物按序号写入同一个目录。常见文件包括：

- `01_profile.json`: 本次申请者画像。
- `02_relevant_pages.json`: 页级筛选诊断。
- `03_clean.md`: PDF 清洗后的 Markdown。
- `04_chunks.json`: chunk 切分结果。
- `05_selected_chunks.json`: profile/cursor 选中的候选证据。
- `06_retrieval.json`: 检索补充结果。
- `07_retrieval_crosscheck.html`: 关键词检索和向量/混合检索的交叉验证视图。
- `07_structured.json`: LLM batch 返回并合并后的结构化事实。
- `08_report.md`: 本地 reporter 生成的规则型报告。
- `09_base_facts.json`: 不依赖申请者画像的文档事实整理，可跨 TOEIC/TOEFL 等 profile 变化复用。
- `09_applicability.json`: LLM 适用性判断。
- `10_llm_report.md`: LLM 生成的自然语言报告。

报告质量问题通常不要只看最终 Markdown，要回到 selected chunks、retrieval cross-check、structured JSON 和 applicability JSON 一起定位。

## 画像配置

推荐使用 `configs/applicant_profile.example.yaml`：

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

也可以直接用 CLI：

```powershell
.\.venv\Scripts\python.exe -m admission_parser.profile_pipeline samples\2027_4_2026_9_master.pdf `
  --target-college 環境・社会理工学院 `
  --degree-level master `
  --exam-type general `
  --english-test toeic `
  --background jp_undergrad `
  --dry-run
```

## 项目结构

```text
.
├─ configs/                  # profile 示例配置
├─ docs/                     # 产品主线、roadmap、实验记录
├─ models/                   # 本地模型，不提交
├─ outputs/                  # 运行产物，不提交
├─ samples/                  # PDF 样本，不提交
├─ scripts/                  # 辅助脚本
├─ src/admission_parser/     # 核心代码
└─ tests/                    # pytest
```

核心模块：

- `extractor.py`: PDF 文本/表格抽取。
- `chunker.py`: Markdown chunk 切分。
- `profile_input.py`: 申请者画像输入。
- `evidence_selector.py`: profile-guided evidence selection。
- `vector_retriever.py`: n-gram / local embedding retrieval。
- `document_index.py`: 文档索引。
- `reference_resolver.py`: 文档内引用识别。
- `recursive_retriever.py`: 引用扩展检索。
- `llm_parser.py`: category-batched LLM structured extraction。
- `merger.py`: 多 batch JSON 合并。
- `validator.py`: 日期、金额、warning 等后处理。
- `applicability.py`: 画像适用性判断。
- `reporter.py`: 本地 Markdown 报告生成。
- `profile_pipeline.py`: 推荐入口。

## 性能目标

当前 pipeline 仍是 builder prototype，不适合作为线上服务直接每次从零跑。

落地形态应拆成：

```text
Cold Build: 新 PDF 入库，允许 5-30 分钟
Warm Profile: 已有 PDF，新申请者画像，目标 10-30 秒
Hot Query: 缓存命中，目标 1-3 秒
```

也就是说，未来真正面向用户时，主流大学募集要项应该提前完成 PDF extraction、chunking、embedding index、base facts/base extraction 和 logic chain 构建。用户查询时只做 profile matching、applicability 和 report generation。

## GitHub 描述建议

```text
Profile-guided evidence selection and reasoning for long admission PDFs, turning Japanese graduate application guidelines into traceable facts, applicability decisions, and applicant-oriented reports.
```

## 近期开发重点

1. 修正 applicability/report cache key，排除 `llm_cache_hits`、`llm_cache_misses` 等运行态字段。
2. 建立 document-level manifest，统一 `pdf_hash`、`chunker_version`、`prompt_version`、`schema_version`。
3. 实装 reasoning-chain MVP，让 LLM 输出 question、answer、reasoning_steps、evidence、uncertainty。
4. 用 Gemini 生成的高质量报告作为 gold sample，对齐覆盖项和表达质量。
5. 继续强化 chunk 边界、target locality 和跨页引用处理。
