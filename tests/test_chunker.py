from admission_parser.chunker import chunk_markdown


def test_chunk_by_title():
    chunks = chunk_markdown("## Page 1\n\n【出願期間】\n本文\n\n１．提出書類\n書類", "sample.pdf", max_chars=1000)
    assert chunks
    assert chunks[0].pdf_name == "sample.pdf"


def test_chunk_splits_section_on_page_boundaries():
    markdown = """【代数系分野】
## Page 20

数理・計算科学系 数理・計算科学コース

## Page 21

理学院 物理学系
筆答試験 8月18日
"""

    chunks = chunk_markdown(markdown, "sample.pdf", max_chars=1000)

    assert len(chunks) == 2
    assert chunks[0].page_numbers == [20]
    assert "数理・計算科学系" in chunks[0].text
    assert "物理学系" not in chunks[0].text
    assert chunks[1].page_numbers == [21]
    assert "物理学系" in chunks[1].text
    assert "数理・計算科学系" not in chunks[1].text
