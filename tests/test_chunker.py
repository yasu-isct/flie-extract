from admission_parser.chunker import chunk_markdown


def test_chunk_by_title():
    chunks = chunk_markdown("## Page 1\n\n【出願期間】\n本文\n\n１．提出書類\n書類", "sample.pdf", max_chars=1000)
    assert chunks
    assert chunks[0].pdf_name == "sample.pdf"
