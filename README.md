# Desearch SERP Rank Checker Example

Made by Desearch | https://desearch.ai

A small Python command-line tool that takes a list of keywords and one domain, calls the Desearch API web search endpoint (`GET https://api.desearch.ai/web`) for each keyword, removes duplicate URLs and reports the best rank your domain got in the results. A later run can be diffed against an earlier one. Output is a CSV, JSON and a short text table. Python standard library only.

It does not claim to match the ranking of any particular search engine. It reports the results the Desearch API returned at the time of the run.

Latest live run: 2026-10-17, see [samples/live-run-2026-10-17.md](samples/live-run-2026-10-17.md).

## What it does

- Reads keywords from a text file (one per line; blank lines, `#` comments and repeats are skipped, so no paid call is made for a blank query).
- For each keyword, calls `GET /web` with `query` and `start` only, by default at `start=0` and `start=20` (see "Why `--step 20`").
- Merges the pages, drops repeated URLs (ignoring `www.`, trailing slashes, `utm_*`, `gclid`, `fbclid`) and numbers the rest 1, 2, 3...
- Reports the first result whose host is your domain or a subdomain of it. `--domain` takes `example.com` or a full URL such as `https://www.example.com/`.
- With `--diff`, compares best ranks against an earlier `summary.json`: `up N`, `down N`, `same`, `entered`, `dropped out`, plus `not checked` for keywords that were only in the earlier run and `new keyword` for ones only in this run.
- A failed call (HTTP error or network error) is shown as `error: HTTP <code> at start=<n>`, never as a rank, and the CLI exits with code 1.
- Paging plans the API would reject (`start` above 100) are refused before any call.

## Requirements

- Python 3.9 or newer.
- A Desearch API key from [console.desearch.ai](https://console.desearch.ai).

## Install

```bash
git clone https://github.com/Desearch-ai/desearch-serp-rank-checker-example
cd desearch-serp-rank-checker-example
python3 -m venv .venv && . .venv/bin/activate
python3 -m pip install -r requirements.txt   # only pytest, for the tests
```

## Set your API key

Use one of these:

```bash
export DESEARCH_API_KEY=your-api-key
# or keep the key in a file outside the repo
export DESEARCH_API_KEY_FILE=$HOME/.config/desearch/api_key
```

`DESEARCH_API_KEY` wins if both are set. The tool sends the key in the `Authorization` header and never writes it to disk: saved calls show `Authorization: <redacted>`, and the client refuses to write any file that contains the key.

## Run

```bash
python3 rank_check.py --keywords samples/keywords.txt --domain desearch.ai
# later: a shorter list, diffed against the first run
python3 rank_check.py --keywords samples/keywords-short.txt --domain desearch.ai --diff runs/<first-run>/summary.json
```

Options: `--pages` (calls per keyword, default 2), `--step` (offset between calls, default 20), `--out` (default `runs/`, which is in `.gitignore`).

Each run writes `runs/<timestamp>/`:

- `results.csv`: keyword, rank, title, url, domain, page_start.
- `results.json`: the same rows plus per-page stats.
- `summary.json`: best rank per keyword, per-page new and duplicate counts, errors, call count, the cost total from the `X-Desearch-Cost-Usd` header, and the diff if asked.
- `calls.jsonl` and `raw/`: every request and response with the billing headers, key redacted.

## Why `--step 20`

The API docs say `start=10` is the 2nd page. In our runs a `GET /web` call returned up to about 20 results, so `start=10` mostly repeats the first call: on 2026-10-17, `serp api` at `start=10` shared 14 of its 21 URLs with `start=0`, while `start=20` shared 4 of 20. The default walks 0, 20. Duplicates are removed either way, and `summary.json` shows how many new URLs each call added.

## Tests

```bash
python3 -m pytest -q
```

21 offline tests (no network, no key): URL and domain matching, paging limits, merge and rank, CSV, diff (including shorter keyword lists), error labels, the CLI end to end with a fake client, key loading, network errors and the key-redaction guard.

## Files

- `rank_check.py`: the CLI and the Desearch client.
- `core.py`: matching, merging, ranking, diff and CSV. No network.
- `tests/`: offline tests.
- `samples/keywords.txt`, `samples/keywords-short.txt`: the keyword lists used in the live run.
- `samples/live-run-2026-10-17.md`: the live run behind the samples, with timestamps and costs.
- `samples/summary-2026-10-17.json`: full summary of the 10-keyword run.
- `samples/diff-summary-2026-10-17.json`: the 5-keyword run diffed against it.
- `samples/results-web-search-api-2026-10-17.csv`: the top 20 rows for one keyword, as returned.

## Cost

Each `GET /web` call was billed $0.001 (`X-Desearch-Cost-Usd: 0.001`, `X-Desearch-Usage-Count: 1`) on 2026-10-16 and 2026-10-17, whatever the number of results. 10 keywords with 2 calls each is 20 calls, $0.02 per run. The CLI prints the cost of each call and the run total.

## Known issues

Seen in our own runs, with dates:

- A blank `query` and a negative `start` return HTTP 200 with an empty list and are billed $0.001 each (2026-10-16 and 2026-10-17). The CLI never sends either. `start` above 100 returns a 422 and is not billed.
- `start=10` overlaps heavily with `start=0` (14 of 21 URLs shared on 2026-10-17), hence the default step of 20.
- The number of results per call varies with no way to set it: 5 to 21 on 2026-10-17 (`x posts search api` returned 5 and 6).
- Results can change between runs a minute apart: on 2026-10-17 a desearch.ai page ranked 16 for `decentralized search engine` at 14:11 and was not in the top 37 at 14:12. Check a keyword twice before acting on one move.
- A query that matches nothing sensible still returns about 20 loosely related results rather than an empty list (2026-10-16), so "not in top N" is the useful signal.
- The OpenAPI file documents success as HTTP 201; every successful call returned 200 (2026-10-17).

## No-code option

The Desearch MCP server offers the same web search as its `web-search` tool (MCP docs checked 2026-10-16), so you can ask an agent in your editor for the results of one keyword without this script.

## License

MIT. See [LICENSE](LICENSE).
