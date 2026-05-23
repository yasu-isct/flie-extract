from admission_parser.chunker import TextChunk
from admission_parser.llm_parser import CATEGORY_RESPONSE_MODELS, _focused_to_admission_info
from admission_parser.schemas import DocumentExtraction, RequiredDocument


def test_category_response_model_mapping():
    assert CATEGORY_RESPONSE_MODELS["documents"] is DocumentExtraction


def test_focused_result_converts_to_admission_info():
    result = DocumentExtraction(required_documents=[RequiredDocument(name="成績証明書")])
    info = _focused_to_admission_info(result)
    assert len(info.required_documents) == 1
    assert info.required_documents[0].name == "成績証明書"
    assert info.application_periods == []


def test_chunk_can_be_constructed_for_routing():
    chunk = TextChunk("x.pdf", [1], "提出書類", "成績証明書を提出する。")
    assert chunk.title == "提出書類"
