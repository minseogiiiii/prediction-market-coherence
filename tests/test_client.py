from prediction_market_coherence.client import KalshiClient


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.calls = []
        self._responses = [
            FakeResponse({"markets": [{"ticker": "A"}], "cursor": "next-page"}),
            FakeResponse({"markets": [{"ticker": "B"}], "cursor": ""}),
        ]

    def get(self, url, params, timeout):
        self.calls.append((url, dict(params), timeout))
        return self._responses.pop(0)


def test_client_follows_cursor_pagination():
    client = KalshiClient()
    fake = FakeSession()
    client.session = fake

    markets = list(client.iter_markets(status="open"))

    assert [m["ticker"] for m in markets] == ["A", "B"]
    assert fake.calls[0][1]["limit"] == 1000
    assert fake.calls[0][1]["mve_filter"] == "exclude"
    assert "cursor" not in fake.calls[0][1]
    assert fake.calls[1][1]["cursor"] == "next-page"
