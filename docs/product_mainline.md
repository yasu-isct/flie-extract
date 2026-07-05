# 产品主线：Profile-Guided Admission Document Intelligence

## 当前定位

本项目不是单次 PDF 总结工具，而是一个面向日本留学生申请场景的长文档智能解析原型。

核心目标是把大学院募集要项从“长 PDF”转成可查询、可追溯、可复用的申请知识底稿，再根据不同申请者画像生成个性化判断和报告。

当前样例是东京科学大学大学院募集要项，但主线目标应保持泛化：

- 适配不同大学、不同格式的募集要项。
- 降低长文档解析 token 和等待成本。
- 支持本地 embedding、小模型、本地化部署的后续路线。
- 保留证据页码、中间产物和缓存，方便复核与迭代。

## 不再追求的方向

后续不建议把系统继续做成“固定字段补丁机”。

如果每遇到一个学校格式就新增字段和专用规则，项目会逐渐变成单校募集要项解析器，难以泛化，也难以维护。

应避免的路线：

- 为单个学校硬编码学院构成字段。
- 为单个 PDF 格式硬编码 A/B 日程位置。
- 只靠本地模板拼报告。
- 只追求一次性漂亮报告，而缺少证据链和缓存。

## 推荐主线

下一阶段应从 profile-first field extraction，升级为 evidence + question + logic-chain extraction。

推荐主线：

```text
PDF
 -> Evidence Index
 -> Question Plan
 -> Recursive Evidence Gathering
 -> Logic Chain Synthesis
 -> Applicability Pass
 -> Narrative Report
```

### 1. Evidence Index

把 PDF 切成更干净的 evidence units：

- page
- title
- section
- chunk_id
- text
- anchors
- references
- neighboring chunks
- source_pages

当前已有基础：

- PyMuPDF + pdfplumber extraction
- chunker
- page boundary split
- document_index
- reference_links
- local embedding retrieval

短期重点是继续减少 chunk 污染，让不同学院、不同系、不同页的内容不要错误混在同一个 evidence unit 里。

### 2. Question Plan

不要只问“抽哪些字段”，而是根据申请者画像生成申请决策问题。

典型问题：

- 我能报哪些学院/系/课程？
- 我的出願資格是什么？
- 我是否需要事前资格审查？
- 我需要哪些材料？
- 我可以用 TOEIC/TOEFL/IELTS 吗？
- 成绩有效期和提交方式是什么？
- 出愿截止日期是什么？
- 目标系适用 A 日程还是 B 日程？
- 笔试/口试/合格发表时间是什么？
- 哪些内容需要人工确认？

这些问题比固定 schema 更能跨学校复用。

### 3. Recursive Evidence Gathering

每个问题先检索证据。如果证据里出现引用、跳转或条件，再继续追。

例：

```text
命中：海外大学卒業 → 下記（3）
追踪：（3）的实际条文
补充：相关证明材料、资格审查条件、例外规则
```

后续优化待办：

- 轻量文档图谱。
- 更深的递归检索。
- section-neighbor expansion。
- condition-driven follow-up retrieval。

### 4. Logic Chain Synthesis

LLM 不只返回字段，而是返回可复核的逻辑链。

建议格式：

```json
{
  "question": "日本本科 + TOEIC 是否需要提交英语成绩？",
  "answer": "需要提交 TOEIC L&R 成绩单。",
  "confidence": "medium",
  "reasoning_steps": [
    "用户画像为日本本科背景，目标为环境・社会理工学院。",
    "募集要项允许 TOEIC L&R 成绩。",
    "规则写明数学系以外全系适用。",
    "目标学院不属于数学系，因此原则上适用。"
  ],
  "evidence": [
    {"page": 11, "text": "TOEIC L&R ..."},
    {"page": 12, "text": "数学系を除く全系 ..."}
  ],
  "uncertainty": "仍需确认目标系是否有单独英语成绩提交规定。"
}
```

这能解释结论来源，也能暴露证据不足的位置。

### 5. Applicability Pass

对 base facts / logic chains 做画像适用性判断。

输入：

- structured JSON
- evidence chains
- applicant profile

输出：

- applies
- not_applicable
- uncertain
- reason
- source_pages
- next_actions

当前已有 MVP：

- `src/admission_parser/applicability.py`
- `09_base_facts.json`
- `09_applicability.json`
- `10_llm_report.md`

### 6. Narrative Report

最终报告应由结构化事实和逻辑链生成，而不是从 PDF 直接自由发挥。

报告目标：

- 自然中文。
- 保留关键页码和证据。
- 对不确定内容明确标注“需要确认”。
- 以申请行动为导向。
- 避免编造未出现的信息。

## 性能主线

当前 pipeline 是 builder 原型，不适合作为在线服务直接运行。

落地形态应拆成离线构建和在线查询。

### Cold Build

新 PDF 首次入库：

```text
PDF extraction
chunking
document index
reference links
embedding index
base extraction
logic chains
```

允许耗时：

```text
5-30 分钟
```

### Warm Profile

已有 PDF，新申请者画像：

```text
profile -> retrieve cached evidence/chains -> applicability -> report
```

目标耗时：

```text
10-30 秒
```

### Hot Query

已有 PDF + 相似 profile + report cache 命中：

```text
读取缓存 -> 返回报告
```

目标耗时：

```text
1-3 秒
```

## 缓存主线

需要逐步稳定这些缓存：

- `document_cache`: pdf_hash -> clean markdown / chunks / page profile
- `embedding_index`: chunk_id -> vector
- `base_extraction_cache`: document_id -> structured facts / logic chains
- `profile_result_cache`: document_id + profile_hash -> applicability result
- `report_cache`: document_id + profile_hash + report_style -> report

当前已有：

- local embedding cache
- LLM extraction cache
- profile-independent base facts cache
- applicability/report cache MVP

待修：

- document-level manifest 和 base facts cache 继续合并到统一缓存管理层。
- 统一 pdf_hash / chunker_version / prompt_version / schema_version。

## 小模型与本地化路线

本地小模型不应直接读整本 PDF。

更合适的路线：

```text
离线用大模型生成高质量 evidence chains / reports
人工抽查修正
积累训练样本
用 7B/8B 模型做 LoRA
在线只喂短 evidence，输出 applicability / chain answer / report section
```

适合蒸馏的小任务：

- evidence reranking
- applicability decision
- logic-chain answer
- report section drafting

不适合早期蒸馏的任务：

- 整本 PDF 长上下文解析
- 无证据自由生成完整报告
- 高风险资格判断

## 当前优先级

短期优先：

1. 稳定 chunk 边界，减少跨页/跨系污染。
2. 继续推进 base facts / applicability / report 的分层缓存。
3. 新增 reasoning chain MVP。
4. 用 Gemini 生成的高质量报告作为 gold sample，对齐报告覆盖项。
5. 写实验记录，比较：
   - Gemini 直接长上下文报告
   - 当前 profile pipeline
   - reasoning-chain pipeline

中期优先：

1. base extraction mode。
2. document-level manifest。
3. profile result cache。
4. 主流大学募集要项离线向量库。

长期优先：

1. 小模型 LoRA / 蒸馏。
2. 本地推理服务。
3. 多大学、多年度、低延迟在线查询。
