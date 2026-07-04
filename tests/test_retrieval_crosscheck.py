import json

from admission_parser.chunker import TextChunk
from admission_parser.retrieval_crosscheck import (
    compare_retrieval_backends,
    write_crosscheck_html,
    write_crosscheck_json,
    write_crosscheck_markdown,
)


class FakeEmbeddingModel:
    def encode(self, texts, normalize_embeddings=True, show_progress_bar=False):
        vectors = []
        for text in texts:
            lower = text.lower()
            if "shared" in lower:
                vectors.append([1.0, 0.0])
            elif "semantic" in lower:
                vectors.append([0.95, 0.0])
            else:
                vectors.append([0.0, 1.0])
        return vectors


def test_compare_retrieval_backends_splits_overlap_and_disagreements():
    chunks = [
        TextChunk("x.pdf", [1], "shared", "shared keyword semantic"),
        TextChunk("x.pdf", [2], "keyword", "keyword keyword keyword"),
        TextChunk("x.pdf", [3], "semantic", "semantic semantic semantic"),
    ]

    payload = compare_retrieval_backends(
        chunks,
        ["shared keyword"],
        top_k=2,
        per_query_k=2,
        embedding_model=FakeEmbeddingModel(),
    )

    assert payload["summary"]["ngram_selected"] == 2
    assert payload["summary"]["embedding_selected"] == 2
    assert payload["summary"]["overlap"] == 1
    assert payload["summary"]["only_ngram"] == 1
    assert payload["summary"]["only_embedding"] == 1
    assert payload["overlap"][0]["index"] == 0
    assert payload["only_ngram"][0]["index"] == 1
    assert payload["only_embedding"][0]["index"] == 2
    assert payload["category_summary"]["general"]["overlap"] == 1
    assert payload["query_summary"][0]["only_ngram"] == 1
    assert payload["query_summary"][0]["only_embedding"] == 1


def test_crosscheck_writers_create_json_markdown_and_html(tmp_path):
    chunks = [
        TextChunk("x.pdf", [1], "shared", "shared keyword semantic"),
        TextChunk("x.pdf", [2], "keyword", "keyword keyword keyword"),
        TextChunk("x.pdf", [3], "semantic", "semantic semantic semantic"),
    ]
    payload = compare_retrieval_backends(
        chunks,
        ["shared keyword"],
        top_k=2,
        per_query_k=2,
        embedding_model=FakeEmbeddingModel(),
    )
    json_output = tmp_path / "crosscheck.json"
    markdown_output = tmp_path / "crosscheck.md"
    html_output = tmp_path / "crosscheck.html"

    write_crosscheck_json(payload, json_output)
    write_crosscheck_markdown(payload, markdown_output)
    write_crosscheck_html(payload, html_output)

    assert json.loads(json_output.read_text(encoding="utf-8"))["summary"]["overlap"] == 1
    markdown = markdown_output.read_text(encoding="utf-8")
    assert "# Retrieval Crosscheck" in markdown
    assert "| category | source | ngram | embedding | overlap | only_ngram | only_embedding |" in markdown
    assert "## Only Embedding" in markdown
    html = html_output.read_text(encoding="utf-8")
    assert "<title>Retrieval Crosscheck</title>" in html
    assert "Category Summary" in html
    assert "Only Embedding" in html
