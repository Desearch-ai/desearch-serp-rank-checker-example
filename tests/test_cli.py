"""Offline tests for the CLI: a fake client stands in for the Desearch API."""
import json, pathlib

import pytest

import rank_check


def page(*hosts):
    return {"data": [{"title": f"T {h}", "link": f"https://{h}/", "snippet": "s"} for h in hosts]}


class FakeClient:
    """Answers GET /web from a dict {(query, start): (status, body)}."""
    script = {}

    def __init__(self, key, out):
        self.key, self.out, self.n, self.total, self.calls = key, pathlib.Path(out), 0, 0.0, []
        self.out.mkdir(parents=True, exist_ok=True)

    def get(self, path, params, tag):
        self.n += 1
        self.calls.append((path, dict(params)))
        st, body = self.script.get((params["query"], params["start"]), (200, {"data": []}))
        self.total += 0.001 if st == 200 else 0.0
        return st, body


@pytest.fixture
def run(tmp_path, monkeypatch):
    monkeypatch.setenv("DESEARCH_API_KEY", "TESTKEY")
    made = []

    def factory(key, out):
        c = FakeClient(key, out)
        made.append(c)
        return c

    def go(keywords, *args, script=None):
        FakeClient.script = script or {}
        kw = tmp_path / "kw.txt"
        kw.write_text(keywords)
        rc = rank_check.main(["--keywords", str(kw), "--out", str(tmp_path / "runs"), *args], client_factory=factory)
        out = made[-1].out
        return rc, json.loads((out / "summary.json").read_text()), made[-1], out
    return go


def test_ranks_dedupes_and_sends_only_query_and_start(run):
    script = {("k", 0): (200, page("a.com", "www.me.dev", "b.com")), ("k", 20): (200, page("a.com", "c.com", "docs.me.dev"))}
    rc, s, c, out = run("k\n", "--domain", "https://www.me.dev/", script=script)
    assert rc == 0 and s["domain"] == "me.dev" and s["starts"] == [0, 20]
    k = s["keywords"][0]
    assert k["best_rank"] == 2 and k["depth"] == 5 and k["page_stats"][1] == {"start": 20, "returned": 3, "new": 2, "dupes": 1}
    assert [p for _, p in c.calls] == [{"query": "k", "start": 0}, {"query": "k", "start": 20}]
    assert all(set(p) == {"query", "start"} for _, p in c.calls)  # no exclude_domains or other filters
    assert (out / "results.csv").read_text().splitlines()[0] == "keyword,rank,title,url,domain,page_start"


def test_api_error_is_reported_not_ranked(run):
    script = {("k", 0): (503, {"detail": "busy"}), ("k", 20): (503, {"detail": "busy"})}
    rc, s, _, _ = run("k\n", "--domain", "me.dev", script=script)
    assert rc == 1 and s["keywords"][0]["label"] == "error: HTTP 503 at start=0"
    assert s["keywords"][0]["errors"] == [{"start": 0, "status": 503}, {"start": 20, "status": 503}]


def test_diff_with_subset_of_keywords(run, tmp_path):
    old = tmp_path / "old.json"
    old.write_text(json.dumps({"keywords": [{"keyword": "k", "best_rank": 3}, {"keyword": "other", "best_rank": 4}]}))
    script = {("k", 0): (200, page("a.com", "me.dev"))}
    rc, s, _, _ = run("k\n", "--domain", "me.dev", "--pages", "1", "--diff", str(old), script=script)
    assert {d["keyword"]: d["change"] for d in s["diff"]} == {"k": "up 1", "other": "not checked"}


def test_bad_paging_fails_before_any_call(run, tmp_path, capsys):
    with pytest.raises(SystemExit):
        run("k\n", "--domain", "me.dev", "--pages", "7", "--step", "20")
    assert "start up to 100" in capsys.readouterr().err
    assert not (tmp_path / "runs").exists()


def test_key_from_env_or_file(tmp_path, monkeypatch):
    f = tmp_path / "k"
    f.write_text("FILEKEY\n")
    monkeypatch.delenv("DESEARCH_API_KEY", raising=False)
    monkeypatch.setenv("DESEARCH_API_KEY_FILE", str(f))
    assert rank_check.api_key() == "FILEKEY"
    monkeypatch.setenv("DESEARCH_API_KEY", "ENVKEY")
    assert rank_check.api_key() == "ENVKEY"
    monkeypatch.delenv("DESEARCH_API_KEY")
    monkeypatch.delenv("DESEARCH_API_KEY_FILE")
    with pytest.raises(SystemExit):
        rank_check.api_key()


def test_client_refuses_key(tmp_path):
    c = rank_check.Client("SECRETKEY123", tmp_path)
    with pytest.raises(RuntimeError):
        c._save(tmp_path / "x.json", {"a": "SECRETKEY123"})


def test_client_network_error_is_status_0(tmp_path, monkeypatch):
    import urllib.error
    def boom(*a, **k):
        raise urllib.error.URLError("no route")
    monkeypatch.setattr(rank_check.urllib.request, "urlopen", boom)
    c = rank_check.Client("SECRETKEY123", tmp_path)
    st, body = c.get("/web", {"query": "k", "start": 0}, "k-s0")
    assert st == 0 and body["error"] == "URLError"
    rec = json.loads((tmp_path / "calls.jsonl").read_text())
    assert rec["request"]["headers"]["Authorization"] == "<redacted>"


def test_slug_fallback():
    assert rank_check.slug("Search API for LLM!") == "search-api-for-llm"
    assert rank_check.slug("поиск") == "kw"
