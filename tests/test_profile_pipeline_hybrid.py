from admission_parser.chunker import TextChunk
from admission_parser.profile_pipeline import _merge_and_balance_chunks


def test_hybrid_merge_keeps_base_and_supplements_without_duplicates():
    base = [
        TextChunk("x.pdf", [1], "出願期間", "出願期間は6月1日から6月10日まで。"),
        TextChunk("x.pdf", [2], "提出書類", "成績証明書を提出する。"),
    ]
    supplement = [
        TextChunk("x.pdf", [2], "提出書類", "成績証明書を提出する。"),
        TextChunk("x.pdf", [3], "英語", "TOEFL iBT のスコアを提出する。"),
    ]
    selected = _merge_and_balance_chunks(base, supplement)
    assert len(selected) == 3
    assert any(chunk.page_numbers == [1] for chunk in selected)
    assert any(chunk.page_numbers == [3] for chunk in selected)
