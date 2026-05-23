# 日本大学院募集要項 PDF 解析器

目标：输入日本大学院募集要項 PDF，输出包含出願期间、材料清单、考试安排、费用、英语要求等信息的结构化 JSON。

## 当前实现范围

本仓库先落地阶段一 MVP，并给阶段二、三预留入口：

1. 双引擎 PDF 探查：PyMuPDF + pdfplumber。
2. 关键词筛选目标页，并输出页面结构 profile。
3. 文本、block、表格提取，表格转换为 Markdown。
4. 按日文标题切片，保留页码、PDF 名、标题元数据。
5. Pydantic 精细 Schema。
6. Instructor + OpenAI 结构化抽取接口。
7. 后处理校验：日期顺序、元号转换、必填字段检查。
8. 阶段二/三模块入口：爬虫、更新检测、SQLite、diff、通知、定时任务。

## 快速开始

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

如需使用 LLM：

```powershell
$env:OPENAI_API_KEY="你的 key"
$env:OPENAI_MODEL="gpt-4.1-mini"
```

准备样本 PDF：把东大、早大、NAIST 等不同排版的募集要項 PDF 放入 `samples/`。PDF 文件会被 `.gitignore` 排除。

## 基础验证

```powershell
python test_env.py samples\your_sample.pdf --check-llm
```

## 阶段一解析流程

完整解析：

```powershell
python -m admission_parser.pipeline samples\your_sample.pdf --output outputs\your_sample.json
```

如果暂时没有 API Key，可以先跑 profile 和 chunk：

```powershell
python -m admission_parser.profiler samples\your_sample.pdf --output outputs
python -m admission_parser.extractor samples\your_sample.pdf --output outputs\clean.md
python -m admission_parser.chunker outputs\clean.md --pdf-name your_sample.pdf --output outputs\chunks.json
```

## 项目结构

```text
src/admission_parser/
  schemas.py        # Pydantic 输出 Schema
  profiler.py       # 目标页筛选和结构探查
  extractor.py      # 双引擎文本/表格提取与清洗
  chunker.py        # 标题感知切片
  llm_parser.py     # Instructor 结构化抽取
  merger.py         # 多切片结果合并去重
  validator.py      # 后处理校验
  pipeline.py       # 阶段一主控流程
  stage2/           # 爬虫、更新检测、SQLite
  stage3/           # diff、通知、定时任务
```

## Git 注意

当前机器未检测到 `git` 命令。安装 Git 后，在项目根目录执行：

```powershell
git init
git add .
git commit -m "Initial admission PDF parser MVP"
```

## 后续路线

- 阶段一增强：加入 3 份 PDF 人工标准答案，计算字段准确率和遗漏率。
- 阶段二增强：补 Playwright failover、断点续传、温和爬取策略细化。
- 阶段三增强：LLM 变更摘要、Slack/飞书卡片、Streamlit 看板、纠错回流。
