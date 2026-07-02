from admission_parser.chunker import TextChunk
from admission_parser.profile_input import ApplicantProfileV2
from admission_parser.vector_retriever import build_profile_queries, retrieve_chunks


def test_build_profile_queries_uses_profile_terms():
    profile = ApplicantProfileV2(
        target_college=["情報理工学院"],
        target_department=["情報工学系"],
        english_test="toefl",
        background="cn_undergrad",
    )
    queries = build_profile_queries(profile)
    joined = "\n".join(queries)
    assert "情報工学系" in joined
    assert "TOEFL" in joined
    assert "中国" in joined


def test_retrieve_chunks_returns_semantic_matches():
    chunks = [
        TextChunk("x.pdf", [1], "検定料", "入学検定料は30,000円。クレジットカードで支払う。"),
        TextChunk("x.pdf", [2], "英語", "TOEFL iBT のスコアを提出する。DIコードを設定する。"),
        TextChunk("x.pdf", [3], "無関係", "キャンパスマップと交通案内。"),
    ]
    selected, decisions = retrieve_chunks(chunks, ["TOEFL スコア DIコード"], top_k=1, per_query_k=2)
    assert len(selected) == 1
    assert selected[0].page_numbers == [2]
    assert decisions[0]["score"] > 0
