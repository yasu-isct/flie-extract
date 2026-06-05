# GitHub Project Description

## Short Description

English:

```text
Profile-guided cursor extraction for long administrative PDFs: compresses LLM input and converts Japanese graduate admission guidelines into structured JSON and readable reports.
```

日本語:

```text
プロファイル誘導型カーソル抽出により長文PDFのLLM入力を圧縮し、日本の大学院募集要項を構造化JSONと可読レポートへ変換する情報抽出プロジェクト。
```

## Portfolio Summary

English:

This project is an end-to-end long-document information extraction system. It uses Japanese graduate admission guideline PDFs as a realistic testbed, but the main technical focus is profile-guided cursor extraction: turning user conditions into extraction cursors, reducing unnecessary chunks before LLM calls, and then applying category-specific Pydantic schemas for structured JSON output.

The system combines PyMuPDF and pdfplumber for PDF parsing, rule-based profiling and chunking, profile/cursor-based input compression, OpenAI-compatible LLM extraction, schema validation, deduplication, and human-readable report generation. In the current sample, cursor selection reduced LLM candidate chunks from 123 to 51 before extraction.

日本語:

本プロジェクトは、長文 PDF に対するエンドツーエンドの情報抽出システムです。日本の大学院募集要項を現実的な評価対象として用いながら、主な技術テーマはプロファイル誘導型カーソル抽出にあります。ユーザー条件を抽出カーソルに変換し、LLM に渡す前に不要なチャンクを削減したうえで、カテゴリ別の Pydantic Schema により構造化 JSON を生成します。

PDF 解析には PyMuPDF と pdfplumber を併用し、ページプロファイリング、チャンク化、プロファイル/カーソルによる入力圧縮、OpenAI 互換 LLM による抽出、Schema 検証、重複排除、可読レポート生成までを一つのパイプラインとして実装しています。現在のサンプルでは、LLM 候補チャンクを 123 から 51 へ削減しました。

## Suggested Topics

```text
llm
document-ai
information-extraction
pdf-processing
structured-output
pydantic
long-context
token-compression
japanese-nlp
```
