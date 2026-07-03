from admission_parser.chunker import TextChunk
from admission_parser.profile_input import ApplicantProfileV2
from admission_parser.vector_retriever import build_profile_queries, retrieve_chunks


class FakeEmbeddingModel:
    def encode(self, texts, normalize_embeddings=True, show_progress_bar=False):
        vectors = []
        for text in texts:
            lower = text.lower()
            vectors.append(
                [
                    1.0 if "toefl" in lower else 0.0,
                    1.0 if "fee" in lower else 0.0,
                    1.0 if "schedule" in lower else 0.0,
                ]
            )
        return vectors


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


def test_retrieve_chunks_with_local_embedding_backend():
    chunks = [
        TextChunk("x.pdf", [1], "fee", "application fee payment"),
        TextChunk("x.pdf", [2], "english", "TOEFL score submission"),
        TextChunk("x.pdf", [3], "schedule", "exam schedule"),
    ]

    selected, decisions = retrieve_chunks(
        chunks,
        ["TOEFL requirement"],
        top_k=1,
        per_query_k=2,
        backend="local-embedding",
        embedding_model=FakeEmbeddingModel(),
    )

    assert selected[0].page_numbers == [2]
    assert decisions[0]["backend"] == "local-embedding"
    assert decisions[0]["score"] == 1.0
