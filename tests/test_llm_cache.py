from admission_parser.chunker import TextChunk
from admission_parser.llm_parser import parse_category_batch


class FakeCompletions:
    def __init__(self):
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        response_model = kwargs["response_model"]
        return response_model(
            fees=[
                {
                    "amount_yen": 30000,
                    "payment_method": "card",
                    "payment_period": "",
                    "notes": "",
                    "source_pages": [1],
                }
            ]
        )


class FakeChat:
    def __init__(self):
        self.completions = FakeCompletions()


class FakeClient:
    def __init__(self):
        self.chat = FakeChat()


def test_parse_category_batch_reuses_cached_llm_result(tmp_path, monkeypatch):
    fake_client = FakeClient()
    monkeypatch.setattr("admission_parser.llm_parser._client", lambda: fake_client)
    chunks = [TextChunk("x.pdf", [1], "fees", "検定料 30,000円")]
    cache_stats = {"hits": 0, "misses": 0}

    first = parse_category_batch(
        chunks,
        "fees",
        focus="fees only",
        cache_dir=tmp_path,
        cache_stats=cache_stats,
    )
    second = parse_category_batch(
        chunks,
        "fees",
        focus="fees only",
        cache_dir=tmp_path,
        cache_stats=cache_stats,
    )

    assert fake_client.chat.completions.calls == 1
    assert cache_stats == {"hits": 1, "misses": 1}
    assert first[0].fees[0].amount_yen == 30000
    assert second[0].fees[0].amount_yen == 30000
    assert list(tmp_path.glob("*.json"))
