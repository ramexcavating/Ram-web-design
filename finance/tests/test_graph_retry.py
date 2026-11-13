"""Graph client retries transient gateway faults instead of failing the run."""
import pytest

from ramfin.sources import graph
from ramfin.sources.graph import GraphClient, GraphError


class _Resp:
    def __init__(self, status_code, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def request(self, method, url, **kw):
        self.calls += 1
        return self.responses.pop(0)


def _client(session, monkeypatch):
    monkeypatch.setattr(graph.time, "sleep", lambda s: None)
    c = GraphClient("tenant", "client", "secret", session=session)
    monkeypatch.setattr(c, "token", lambda: "tok")
    return c


def test_502_is_retried_then_succeeds(monkeypatch):
    s = _Session([_Resp(502, '{"error":{"code":"UnknownError"}}'), _Resp(202)])
    r = _client(s, monkeypatch)._req("POST", "/users/x@example.com/sendMail", json={})
    assert r.status_code == 202
    assert s.calls == 2


def test_persistent_502_gives_up(monkeypatch):
    s = _Session([_Resp(502)] * 5)
    with pytest.raises(GraphError, match="gave up"):
        _client(s, monkeypatch)._req("POST", "/users/x@example.com/sendMail", json={})
    assert s.calls == 5


def test_400_is_not_retried(monkeypatch):
    s = _Session([_Resp(400, "bad request")])
    with pytest.raises(GraphError, match="400"):
        _client(s, monkeypatch)._req("POST", "/users/x@example.com/sendMail", json={})
    assert s.calls == 1
