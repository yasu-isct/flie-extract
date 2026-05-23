from admission_parser.chunker import TextChunk
from admission_parser.profile_filter import filter_chunks
from admission_parser.reporter import ApplicantProfile


def test_profile_filter_keeps_target_chunk():
    chunks = [
        TextChunk("x.pdf", [1], "工学院", "電気電子系の試験日程"),
        TextChunk("x.pdf", [2], "情報理工学院", "数理・計算科学系と情報工学系の出願書類"),
    ]
    profile = ApplicantProfile(targets=["情報理工学院", "情報工学系"])
    kept, decisions = filter_chunks(chunks, profile)
    assert len(kept) == 1
    assert kept[0].page_numbers == [2]
    assert decisions[1]["keep"]


def test_profile_filter_keeps_general_deadline():
    chunks = [
        TextChunk("x.pdf", [1], "出願期間", "出願期間は2026年6月4日から6月10日まで。必着。"),
    ]
    profile = ApplicantProfile(targets=["情報理工学院"])
    kept, _ = filter_chunks(chunks, profile)
    assert len(kept) == 1
