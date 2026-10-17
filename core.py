"""Network-free logic for the SERP API Rank Checker. No I/O, no HTTP: easy to unit-test."""
import csv, io, urllib.parse

MAX_START = 100  # GET /web rejects start > 100 with HTTP 422 (OpenAPI, checked 2026-10-17)


def normalize_url(url):
    """Lowercase scheme/host, drop leading www., fragment, trailing slash and common tracking params."""
    p = urllib.parse.urlsplit((url or "").strip())
    host = (p.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True)
         if not k.lower().startswith("utm_") and k.lower() not in ("gclid", "fbclid")]
    path = p.path.rstrip("/") or "/"
    return urllib.parse.urlunsplit(("https", host, path, urllib.parse.urlencode(q), ""))


def domain_of(url):
    host = (urllib.parse.urlsplit((url or "").strip()).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def normalize_domain(domain):
    """Accept 'example.com', 'www.example.com', 'https://www.example.com/page' or 'Example.com.'
    and return the bare host 'example.com'."""
    d = (domain or "").strip().lower()
    if "://" in d:
        d = urllib.parse.urlsplit(d).hostname or ""
    else:
        d = d.split("/", 1)[0].split(":", 1)[0]
    d = d.strip(".")
    return d[4:] if d.startswith("www.") else d


def matches_domain(url, domain):
    """True if url's host is domain or a subdomain of it."""
    d, h = normalize_domain(domain), domain_of(url)
    return bool(d) and (h == d or h.endswith("." + d))


def items_of(body):
    """GET /web returns {"data": [...]}. Anything else yields []."""
    if isinstance(body, dict) and isinstance(body.get("data"), list):
        return [i for i in body["data"] if isinstance(i, dict)]
    return []


def page_starts(pages, step):
    """Start offsets for `pages` pages, `step` apart. Raises ValueError before any paid call
    if the plan is impossible (the API answers start > 100 with a 422)."""
    if pages < 1:
        raise ValueError("--pages must be 1 or more")
    if pages > 1 and step < 1:
        raise ValueError("--step must be 1 or more")
    starts = [p * step for p in range(pages)]
    if starts[-1] > MAX_START:
        raise ValueError(f"last page would start at {starts[-1]}; the API allows start up to {MAX_START}")
    return starts


def merge_pages(pages):
    """pages: list of (start, items) in request order. Returns ranked rows (dedup by normalized URL)
    and per-page stats {start, returned, new, dupes}."""
    seen, rows, stats = set(), [], []
    for start, items in pages:
        new = 0
        for it in items:
            url = it.get("link") or it.get("url") or ""
            key = normalize_url(url)
            if not url or key in seen:
                continue
            seen.add(key)
            new += 1
            rows.append({"rank": len(rows) + 1, "title": (it.get("title") or "").strip(), "url": url,
                         "domain": domain_of(url), "page_start": start})
        stats.append({"start": start, "returned": len(items), "new": new, "dupes": len(items) - new})
    return rows, stats


def best_rank(rows, domain):
    for r in rows:
        if matches_domain(r["url"], domain):
            return r["rank"]
    return None


def rank_label(rank, depth, errors=()):
    if errors and not rank:
        e = errors[0]
        return f"error: HTTP {e['status']} at start={e['start']}" if e["status"] else f"error at start={e['start']}"
    label = str(rank) if rank else f"not in top {depth}"
    return label + " (incomplete)" if errors else label


def keyword_summary(keyword, domain, rows, errors=()):
    br = best_rank(rows, domain)
    hit = next((r for r in rows if r["rank"] == br), None)
    return {"keyword": keyword, "domain": normalize_domain(domain), "best_rank": br,
            "label": rank_label(br, len(rows), errors), "best_url": hit["url"] if hit else "",
            "depth": len(rows), "errors": list(errors)}


def to_csv(results):
    """results: list of {keyword, rows}. One CSV row per result."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["keyword", "rank", "title", "url", "domain", "page_start"])
    for res in results:
        for r in res["rows"]:
            w.writerow([res["keyword"], r["rank"], r["title"], r["url"], r["domain"], r["page_start"]])
    return buf.getvalue()


def diff_runs(old, new):
    """old/new: {keyword: best_rank or None}. Keywords that are only in the old run were not
    checked this time and are reported as "not checked", not as "dropped out"."""
    out = []
    for kw in sorted(set(old) | set(new)):
        a, b = old.get(kw), new.get(kw)
        if kw not in new:
            change = "not checked"
        elif kw not in old:
            change = "new keyword"
        elif a == b:
            change = "same"
        elif a is None:
            change = "entered"
        elif b is None:
            change = "dropped out"
        else:
            change = f"up {a - b}" if b < a else f"down {b - a}"
        out.append({"keyword": kw, "before": a, "after": b, "change": change})
    return out


def url_overlap(rows_a, rows_b, top=10):
    """Share of normalized URLs in the top N of run A that also appear in the top N of run B."""
    a = {normalize_url(r["url"]) for r in rows_a[:top]}
    b = {normalize_url(r["url"]) for r in rows_b[:top]}
    return (len(a & b), len(a))


def parse_keywords(text):
    seen, out = set(), []
    for line in text.splitlines():
        k = line.strip()
        if k and not k.startswith("#") and k.lower() not in seen:
            seen.add(k.lower())
            out.append(k)
    return out
