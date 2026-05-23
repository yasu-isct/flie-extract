from admission_parser.category_router import categorize_chunk, category_counts
from admission_parser.chunker import TextChunk


def test_categorize_english_chunk():
    chunk = TextChunk("x.pdf", [1], "英語外部試験", "TOEFL iBT のスコアシートを提出する。")
    assert categorize_chunk(chunk) == "english"


def test_categorize_documents_chunk():
    chunk = TextChunk("x.pdf", [1], "提出書類", "成績証明書と卒業証明書を提出する。")
    assert categorize_chunk(chunk) == "documents"


def test_category_counts():
    chunks = [
        TextChunk("x.pdf", [1], "検定料", "30,000円を支払う。"),
        TextChunk("x.pdf", [2], "試験", "口述試験を実施する。"),
    ]
    assert category_counts(chunks) == {"exams": 1, "fees": 1}
