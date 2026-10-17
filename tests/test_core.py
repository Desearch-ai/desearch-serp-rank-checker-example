import pytest
import core


def it(url, title="t"):
    return {"link": url, "title": title}


def test_normalize():
    assert core.normalize_url("http://WWW.Ex.com/a/?utm_source=x#f") == "https://ex.com/a"
    assert core.normalize_url("https://ex.com") == "https://ex.com/"


def test_domain_match():
    assert core.matches_domain("https://docs.ex.com/x", "ex.com")
    assert core.matches_domain("https://www.ex.com", "www.ex.com")
    assert not core.matches_domain("https://notex.com", "ex.com")


def test_domain_given_as_url_still_matches():
    # #26 compared the raw --domain string, so "https://www.ex.com/" never matched anything
    for d in ("https://www.ex.com/", "http://Ex.com/pricing", "ex.com.", "EX.COM", "www.ex.com/blog", "ex.com:443"):
        assert core.normalize_domain(d) == "ex.com"
        assert core.matches_domain("https://blog.ex.com/p", d)
    assert core.normalize_domain("  ") == ""


def test_items_of():
    assert core.items_of({"data": [it("https://a.com"), 3]}) == [it("https://a.com")]
    assert core.items_of([1]) == [] and core.items_of({"detail": "x"}) == []


def test_page_starts():
    assert core.page_starts(2, 20) == [0, 20]
    assert core.page_starts(1, 0) == [0]
    assert core.page_starts(6, 20)[-1] == 100
    for pages, step in ((0, 20), (2, 0), (7, 20), (3, 60)):
        with pytest.raises(ValueError):
            core.page_starts(pages, step)


def test_merge_dedupes_and_ranks():
    rows, stats = core.merge_pages([(0, [it("https://a.com"), it("https://b.com")]),
                                    (10, [it("https://www.a.com/"), it("https://c.com")])])
    assert [r["rank"] for r in rows] == [1, 2, 3] and rows[2]["page_start"] == 10
    assert stats[1] == {"start": 10, "returned": 2, "new": 1, "dupes": 1}


def test_merge_keeps_title_unedited():
    rows, _ = core.merge_pages([(0, [it("https://a.com", " Search API \u2014 “Pricing” & docs ")])])
    assert rows[0]["title"] == "Search API \u2014 “Pricing” & docs"


def test_best_rank_and_summary():
    rows, _ = core.merge_pages([(0, [it("https://a.com"), it("https://blog.me.dev/p")])])
    s = core.keyword_summary("k", "me.dev", rows)
    assert s["best_rank"] == 2 and s["label"] == "2" and s["errors"] == []
    assert core.keyword_summary("k", "zz.dev", rows)["label"] == "not in top 2"


def test_error_labels():
    # #26 labelled a failed keyword "not in top 0", which reads like a real result
    assert core.rank_label(None, 0, [{"start": 0, "status": 503}]) == "error: HTTP 503 at start=0"
    assert core.rank_label(None, 0, [{"start": 20, "status": 0}]) == "error at start=20"
    assert core.rank_label(None, 18, [{"start": 20, "status": 429}]) == "error: HTTP 429 at start=20"
    assert core.rank_label(4, 18, [{"start": 20, "status": 429}]) == "4 (incomplete)"


def test_csv():
    rows, _ = core.merge_pages([(0, [it("https://a.com", 'x, "y"')])])
    out = core.to_csv([{"keyword": "k", "rows": rows}])
    assert out.splitlines()[1] == 'k,1,"x, ""y""",https://a.com,a.com,0'


def test_diff():
    d = {x["keyword"]: x["change"] for x in core.diff_runs({"a": 3, "b": None, "c": 2, "d": 1}, {"a": 1, "b": 4, "c": None, "d": 1})}
    assert d == {"a": "up 2", "b": "entered", "c": "dropped out", "d": "same"}


def test_diff_with_fewer_keywords_is_not_dropped_out():
    # #26 reported keywords missing from the new run as "dropped out"
    d = {x["keyword"]: x["change"] for x in core.diff_runs({"a": 3, "b": 5, "c": None}, {"a": 3, "z": 2})}
    assert d == {"a": "same", "b": "not checked", "c": "not checked", "z": "new keyword"}


def test_overlap_and_keywords():
    a, _ = core.merge_pages([(0, [it("https://a.com"), it("https://b.com")])])
    b, _ = core.merge_pages([(0, [it("https://b.com"), it("https://c.com")])])
    assert core.url_overlap(a, b) == (1, 2)
    assert core.parse_keywords("x\n# c\n\nX\ny ") == ["x", "y"]
