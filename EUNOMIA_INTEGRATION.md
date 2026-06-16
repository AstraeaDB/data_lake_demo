# Eunomia + this demo — the working-memory layer in front of AstraeaDB

The orchestrator's three metadata tools (`search_catalog`, `get_source_details`,
`find_related_sources`) make repeated round-trips to AstraeaDB on every LLM
turn. Eunomia is a low-latency semantic cache (exact K/V + HNSW vector recall +
TTL, over REST) that sits in front of those calls so re-asks within a session
hit working memory instead of the catalog.

```
agent ──tool call──► orchestrator ──┬──► Eunomia (hit ~0.3 ms via HTTP) ──► return
                                    └──► AstraeaDB (miss, then store-back)
```

The DuckDB data-plane tools (`list_data_sources`, `preview_data_source`,
`query_data_source`) are deliberately **not** cached — they read freshly from
files on every call, which is what you want for SQL.

## What's cached

| Tool | Strategy | Key |
|---|---|---|
| `search_catalog(query, k)` | **semantic recall** — embedding-keyed; "video conferencing" hits a prior result for "video conferencing data" if similarity ≥ `EUNOMIA_SIM_THRESHOLD` (default 0.97) and the cached `k` ≥ requested `k` | `sc:<sha1(query)[:16]>` |
| `get_source_details(source_name)` | **exact K/V** — sub-ms gets on repeat | `src_details:<source_name>` |
| `find_related_sources(source_name)` | **exact K/V** | `src_related:<source_name>` |

Default TTL is 3600 s — long enough that a multi-turn session never re-pays
the catalog cost for the same source, short enough that a tomorrow run starts
fresh.

## Enabling it

Eunomia is **off by default** — the demo behaves identically without it. To
turn it on, set `EUNOMIA_URL` and run as usual:

```bash
# start Eunomia once (uses eunomia.toml, port 8137)
make start-eunomia

# run the demo with the cache in front
make demo-eunomia
# or, manually:  EUNOMIA_URL=http://127.0.0.1:8137 python3 -m src.orchestrator
```

At startup the orchestrator prints:

```
Eunomia: enabled (url=http://127.0.0.1:8137, sim≥0.97)
```

…and at the end of every run a session report is printed:

```
─────────────────────────────────────────────────────────────────────
  Eunomia metadata cache — session report
─────────────────────────────────────────────────────────────────────
  tool                    calls   hits    hit%    hit ms   miss ms
  ─────────────────────────────────────────────────────────────────
  search_catalog              5      2   40.0%     0.32      0.08
  get_source_details         11      3   27.3%     0.30      0.17
  find_related_sources        4      1   25.0%     0.27      0.13
  ─────────────────────────────────────────────────────────────────
  total: 20 calls, 6 hits (30.0%)
─────────────────────────────────────────────────────────────────────
```

The report prints even on `Ctrl-C` during interactive chat. With Eunomia
disabled, every line shows 0% hits — the same report format, useful as a
baseline.

## Validating the integration: `make bench-eunomia`

A reproducible synthetic harness (no LLM, no Ollama needed) replays the
metadata-call pattern the three demo acts make — including Act 3's revisits of
sources Act 2 touched, and a "video conferencing" search re-phrased three
ways. Run it twice to see both regimes:

```bash
make bench-eunomia      # first run: cold cache → ~30% hits
make bench-eunomia      # immediate replay: warm cache → 100% hits
```

Cold-run output (representative):

```
  tool                    calls   hits    hit%    hit ms   miss ms
  ─────────────────────────────────────────────────────────────────
  search_catalog              5      2   40.0%     0.32      0.08
  get_source_details         11      3   27.3%     0.30      0.17
  find_related_sources        4      1   25.0%     0.27      0.13
  ─────────────────────────────────────────────────────────────────
  total: 20 calls, 6 hits (30.0%)
```

The 40% search_catalog hit rate confirms the **semantic** path works
("video conferencing data" → "video conferencing meetings" → "video
conferencing" all collapse to the same cached entry); the 25-27% exact hit
rates confirm cross-act source revisits land. Warm replay then shows the
mechanics are clean: every one of the 20 calls hits.

## Why the bench doesn't claim a "ms saved" number

The synthetic harness uses the orchestrator's **file fallback** as its miss
path (since AstraeaDB / Ollama may not be running). Reading `sources.json` is
sub-100 µs — fast enough that Eunomia's localhost HTTP round-trip is
comparable, and the cache shows essentially **no wall-time speedup against
that miss baseline**.

That's an artifact of the miss baseline, not the cache. In the real demo —
LLM round-trips, network calls to AstraeaDB, graph traversal — every cached
metadata round-trip you skip is **tens of milliseconds** the agent doesn't
have to wait for. The bench validates the **mechanics** (hit rate, semantic
matching, no spurious misses); end-to-end speedup is measured by running
`make demo-eunomia` against the full pipeline with timing.

## Configuration knobs

| Variable | Default | Effect |
|---|---|---|
| `EUNOMIA_URL` | unset | Bridge disabled; orchestrator behaves as before |
| `EUNOMIA_SIM_THRESHOLD` | `0.97` | Minimum cosine similarity for a `search_catalog` semantic hit |
| `EUNOMIA_BIN` | the dev-env build path | Path to the eunomia binary (Makefile var) |
| `EUNOMIA_PORT` | `8137` | Port the local Eunomia listens on |

## Failure modes (and what happens)

* **Eunomia not started** — the bridge fails its initial handshake and
  reports `disabled`. All calls go straight to AstraeaDB; the demo runs
  exactly as before.
* **Eunomia goes down mid-session** — individual HTTP errors are swallowed
  (cache reports miss), AstraeaDB serves the request. Once Eunomia comes
  back up the next request will succeed.
* **Embedding service down** — `search_catalog` skips the semantic cache and
  uses the existing all-sources fallback (no cache interaction).
* **Source name typo** — same fallback path the demo always took; the typo
  is recorded as a miss with the existing error string.

This is what "fail-open" means: every failure mode degrades to the
pre-Eunomia behavior. The demo never gets worse for having tried the cache.
