# GitHub Project Description

## Short Description

English:

```text
Profile-guided cursor extraction for complex long PDFs: compresses LLM input and converts dense documents into structured JSON and readable reports.
```

日本語:

```text
プロファイル誘導型カーソル抽出により長文PDFのLLM入力を圧縮し、高密度文書を構造化JSONと可読レポートへ変換する汎用情報抽出プロジェクト。
```

## Portfolio Summary

English:

This project is an end-to-end long-document information extraction system based on profile-guided cursor extraction. It turns user conditions into extraction cursors, reduces unnecessary chunks before LLM calls, and then applies category-specific Pydantic schemas for structured JSON output.

The system combines PyMuPDF and pdfplumber for PDF parsing, rule-based profiling and chunking, profile/cursor-based input compression, OpenAI-compatible LLM extraction, schema validation, deduplication, and human-readable report generation. In an evaluation sample, cursor selection reduced LLM candidate chunks from 123 to 51 before extraction.

日本語:

本プロジェクトは、プロファイル誘導型カーソル抽出に基づく長文 PDF 向けのエンドツーエンド情報抽出システムです。ユーザー条件を抽出カーソルに変換し、LLM に渡す前に不要なチャンクを削減したうえで、カテゴリ別の Pydantic Schema により構造化 JSON を生成します。

PDF 解析には PyMuPDF と pdfplumber を併用し、ページプロファイリング、チャンク化、プロファイル/カーソルによる入力圧縮、OpenAI 互換 LLM による抽出、Schema 検証、重複排除、可読レポート生成までを一つのパイプラインとして実装しています。評価用サンプルでは、LLM 候補チャンクを 123 から 51 へ削減しました。

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
