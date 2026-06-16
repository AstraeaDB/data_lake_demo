"""Synthetic harness that exercises the metadata cache.

Replays a representative sequence of metadata calls — the same shapes the LLM
makes during Acts 2 and 3 of the narrated demo — and prints the timing /
hit-rate report at the end. Runs **without an LLM** (no Anthropic key, no
Ollama needed): ``embed_text`` is monkeypatched with a deterministic synthetic
embedding so the cache mechanics are reproducible, and the orchestrator's
file-based fallback path handles the "no AstraeaDB" case.

Run with the cache off (baseline) and on (measured):

    # baseline — no EUNOMIA_URL set
    python3 scripts/bench_eunomia.py

    # measured — Eunomia running at the URL
    EUNOMIA_URL=http://127.0.0.1:8137 python3 scripts/bench_eunomia.py

The report at the end shows per-tool hit rate and mean ms for hits vs misses.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ---- 1. Deterministic synthetic embedding (monkeypatch) ---------------------
#
# The cache check uses cosine similarity; we just need a stable mapping from
# query string to 128-d vector where queries that share a leading topic word
# land in the same dominant basis bucket (and thus hit each other at ≥ 0.97
# similarity), while topically different queries do not.

def _fake_embed(text, model=None, dim=128):
    topic = (text.lower().split() or ["x"])[0]
    bucket = int(hashlib.sha1(topic.encode()).hexdigest()[:8], 16) % dim
    base = [0.0] * dim
    base[bucket] = 1.0
    perturb = int(hashlib.sha1(text.encode()).hexdigest()[:8], 16)
    for i in range(8):
        base[(perturb >> (i * 2)) & (dim - 1)] += 0.04  # small noise
    norm = sum(x * x for x in base) ** 0.5
    return [x / norm for x in base]


from src import embeddings as _emb_module
_emb_module.embed_text = _fake_embed
from src import orchestrator as _orc_module
_orc_module.embed_text = _fake_embed


# ---- 2. Representative metadata trace --------------------------------------
#
# Modeled on the three demo acts. Two important shapes are exercised:
#   • exact re-hits: Act 3 revisits sources Act 2 already touched
#   • semantic re-hits: "video conferencing" later phrased as just "video"
#     should hit the earlier embedding within sim_threshold

TRACE: list[tuple[str, dict]] = [
    # --- Act 2 Q1: video-call trend ---
    ("search_catalog", {"query": "video conferencing data", "k": 10}),
    ("get_source_details", {"source_name": "Microsoft Teams Call Logs"}),
    ("get_source_details", {"source_name": "Zoom Meeting Logs"}),
    ("find_related_sources", {"source_name": "Microsoft Teams Call Logs"}),

    # --- Act 2 Q2: user U0001 security activity ---
    ("search_catalog", {"query": "security authentication events", "k": 10}),
    ("get_source_details", {"source_name": "CERT Logon Events"}),
    ("get_source_details", {"source_name": "Web Proxy HTTP Access Logs"}),
    ("get_source_details", {"source_name": "Email Gateway Activity"}),
    ("find_related_sources", {"source_name": "CERT Logon Events"}),

    # --- Act 3: cross-domain U0001 — many revisits ---
    ("search_catalog", {"query": "video conferencing meetings", "k": 10}),  # semantic re-hit
    ("search_catalog", {"query": "HR employee records", "k": 10}),
    ("get_source_details", {"source_name": "Microsoft Teams Call Logs"}),          # exact re-hit
    ("get_source_details", {"source_name": "Zoom Meeting Logs"}),           # exact re-hit
    ("get_source_details", {"source_name": "CERT Logon Events"}),           # exact re-hit
    ("get_source_details", {"source_name": "Legacy HRIS Employee Records"}),
    ("get_source_details", {"source_name": "Modern HCM Platform Records"}),
    ("get_source_details", {"source_name": "Project Management Tickets"}),
    ("find_related_sources", {"source_name": "Legacy HRIS Employee Records"}),
    ("find_related_sources", {"source_name": "Microsoft Teams Call Logs"}),        # exact re-hit
    ("search_catalog", {"query": "security events log", "k": 10}),          # semantic re-hit
]


# ---- 3. Replay -------------------------------------------------------------

def main() -> None:
    from src.orchestrator import DemoOrchestrator

    print("─" * 76)
    print("  Eunomia bench harness — replaying a representative metadata trace")
    print("─" * 76)
    orchestrator = DemoOrchestrator()
    print(f"  trace length: {len(TRACE)} metadata calls")
    print("─" * 76)

    for i, (tool, args) in enumerate(TRACE, 1):
        out = orchestrator.execute_tool(tool, args)
        first_line = out.splitlines()[0][:60] if out else ""
        print(f"  [{i:>2}/{len(TRACE)}] {tool:<22} {first_line}")

    report = orchestrator.metrics.report()
    if report:
        print(report)
    orchestrator.eunomia.close()


if __name__ == "__main__":
    main()
