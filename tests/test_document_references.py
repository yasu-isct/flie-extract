from admission_parser.chunker import TextChunk
from admission_parser.document_index import build_document_index, extract_anchors, extract_references
from admission_parser.recursive_retriever import expand_chunks_by_references
from admission_parser.reference_resolver import resolve_references


def test_extracts_item_anchors_and_forward_references():
    anchors = extract_anchors("（３）海外の大学を卒業し、学位を取得した者")
    references = extract_references("海外の大学を卒業し、学位を取得 → 下記（３）")

    assert anchors[0].key == "item:3"
    assert references[0].key == "item:3"
    assert references[0].direction == "forward"


def test_resolves_forward_reference_to_later_chunk_and_expands_selection():
    chunks = [
        TextChunk(
            "x.pdf",
            [1],
            "３．出願資格",
            "参考。海外の大学を卒業し、学位を取得 → 下記（３）",
        ),
        TextChunk(
            "x.pdf",
            [1],
            "３．出願資格",
            "（１）日本の大学を卒業した者",
        ),
        TextChunk(
            "x.pdf",
            [2],
            "３．出願資格",
            "（３）外国において学校教育における16年の課程を修了した者",
        ),
    ]

    index = build_document_index(chunks)
    links = resolve_references(index)
    expanded, records = expand_chunks_by_references(chunks, [chunks[0]], links, max_depth=1)

    assert len(links) == 1
    assert links[0].source_chunk_id == 0
    assert links[0].target_chunk_id == 2
    assert [chunk.text for chunk in expanded] == [chunks[0].text, chunks[2].text]
    assert records[0].reference == "下記（３）"
