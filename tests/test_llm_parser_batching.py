from admission_parser.chunker import TextChunk
from admission_parser.llm_parser import combine_chunks_for_category


def test_combine_chunks_for_category_batches_by_size():
    chunks = [
        TextChunk("sample.pdf", [1], "A", "a" * 20),
        TextChunk("sample.pdf", [2], "B", "b" * 20),
        TextChunk("sample.pdf", [3], "C", "c" * 20),
    ]

    batches = combine_chunks_for_category(chunks, category="documents", max_chars=120)

    assert len(batches) >= 2
    assert batches[0].title == "category:documents"
    assert 1 in batches[0].page_numbers
    assert "### Chunk 1" in batches[0].text


def test_combine_chunks_for_category_keeps_pages_sorted():
    chunks = [
        TextChunk("sample.pdf", [3, 1], "A", "alpha"),
        TextChunk("sample.pdf", [2], "B", "beta"),
    ]

    batches = combine_chunks_for_category(chunks, category="english", max_chars=1000)

    assert len(batches) == 1
    assert batches[0].page_numbers == [1, 2, 3]
