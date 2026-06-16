"""Eunomia working-memory bridge for the data-lake demo.

Eunomia is a low-latency semantic cache (https://github.com/AstraeaDB/...).
This module sits in front of the metadata calls the orchestrator makes to
AstraeaDB so repeated discovery turns hit µs-scale working memory instead of
round-tripping through the catalog every time.

Three cache shapes are exposed:

* :py:meth:`EunomiaBridge.recall_semantic` — embedding-keyed semantic cache.
  Different phrasings of the same concept hit the same cache entry. Used by
  ``search_catalog``: a query for "video conferencing data" can hit a prior
  result for "video calls" if the embeddings are similar enough.

* :py:meth:`EunomiaBridge.get_exact` / :py:meth:`EunomiaBridge.store_exact` —
  exact key/value, microsecond hits. Used by ``get_source_details`` and
  ``find_related_sources`` where the input is a stable string (the source name).

The bridge **fails open**: if Eunomia is unreachable, every call reports a miss
and store calls become no-ops, so the demo runs identically without it.
Activation: set ``EUNOMIA_URL`` (default disables the bridge entirely).

A :class:`MetricsCollector` records every operation (tool, hit, elapsed_ms) and
prints a comparison report at the end of the run — that's where the "before vs
after" numbers in the marketing pitch come from.
"""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

import httpx


# ---------- public configuration ---------------------------------------------

DEFAULT_API_KEY = "dev-key"
DEFAULT_NAMESPACE_DIM = 128  # matches the demo's embedding pipeline
DEFAULT_SIM_THRESHOLD = 0.97
DEFAULT_TTL_SECS = 3600


# ---------- metrics ----------------------------------------------------------


@dataclass
class _Sample:
    tool: str
    hit: bool
    source: str  # "eunomia" or "astraea"
    elapsed_ms: float


@dataclass
class MetricsCollector:
    """Records cache-related timing samples and prints a summary report."""

    samples: list[_Sample] = field(default_factory=list)

    def record(self, tool: str, hit: bool, source: str, elapsed_ms: float) -> None:
        self.samples.append(_Sample(tool, hit, source, elapsed_ms))

    @contextmanager
    def measure(self, tool: str, *, source: str, hit: bool) -> Iterator[None]:
        """Time a block and record one sample."""
        start = time.perf_counter()
        try:
            yield
        finally:
            self.record(tool, hit, source, (time.perf_counter() - start) * 1000.0)

    def report(self) -> str:
        """Render a one-screen summary suitable for end-of-run output."""
        if not self.samples:
            return "(no metadata calls recorded)"

        per_tool: dict[str, list[_Sample]] = defaultdict(list)
        for s in self.samples:
            per_tool[s.tool].append(s)

        lines = ["", "─" * 76, "  Eunomia metadata cache — session report", "─" * 76]
        header = f"  {'tool':<22} {'calls':>6} {'hits':>6} {'hit%':>7} {'hit ms':>9} {'miss ms':>9}"
        lines.append(header)
        lines.append("  " + "─" * 72)

        total_calls = total_hits = 0
        total_hit_time = total_miss_time = 0.0
        for tool, samples in per_tool.items():
            calls = len(samples)
            hits = [s for s in samples if s.hit]
            misses = [s for s in samples if not s.hit]
            hit_ms = sum(s.elapsed_ms for s in hits) / len(hits) if hits else 0.0
            miss_ms = sum(s.elapsed_ms for s in misses) / len(misses) if misses else 0.0
            hit_pct = 100.0 * len(hits) / calls if calls else 0.0
            lines.append(
                f"  {tool:<22} {calls:>6} {len(hits):>6} {hit_pct:>6.1f}% "
                f"{hit_ms:>8.2f}  {miss_ms:>8.2f}"
            )
            total_calls += calls
            total_hits += len(hits)
            total_hit_time += sum(s.elapsed_ms for s in hits)
            total_miss_time += sum(s.elapsed_ms for s in misses)

        lines.append("  " + "─" * 72)
        hit_pct = 100.0 * total_hits / total_calls if total_calls else 0.0
        lines.append(f"  total: {total_calls} calls, {total_hits} hits ({hit_pct:.1f}%)")
        # Only claim wall-time savings when the miss baseline is realistic
        # (real network/graph cost, > 1 ms). The synthetic bench's miss path
        # reads JSON files in microseconds — fast enough that the cache's HTTP
        # round-trip looks comparable, which is *not* the real-AstraeaDB
        # regime where misses are tens of ms.
        misses = total_calls - total_hits
        if total_hits and misses:
            mean_miss = total_miss_time / misses
            mean_hit = total_hit_time / total_hits
            if mean_miss >= 1.0:
                saved_ms = (mean_miss - mean_hit) * total_hits
                lines.append(
                    f"  est. saved vs. uncached: {saved_ms:.0f} ms "
                    f"(mean miss {mean_miss:.2f} ms − mean hit {mean_hit:.2f} ms)"
                )
            else:
                lines.append(
                    f"  miss baseline {mean_miss:.2f} ms is too fast to be realistic — "
                    "run against live AstraeaDB to measure end-to-end speedup."
                )
        lines.append("─" * 76)
        return "\n".join(lines)


# ---------- bridge -----------------------------------------------------------


class EunomiaBridge:
    """Thin REST client to a running Eunomia server.

    The bridge is **fail-open**: connection or HTTP errors are swallowed and
    surfaced as cache misses, so the demo behaves correctly without Eunomia.
    """

    def __init__(
        self,
        url: str | None = None,
        api_key: str = DEFAULT_API_KEY,
        sim_threshold: float = DEFAULT_SIM_THRESHOLD,
        ttl_secs: int = DEFAULT_TTL_SECS,
        timeout_ms: int = 250,
    ):
        # `EUNOMIA_URL` is the activation switch — absent ⇒ disabled bridge.
        self.url = (url or os.environ.get("EUNOMIA_URL") or "").rstrip("/")
        self.api_key = api_key
        self.sim_threshold = float(os.environ.get("EUNOMIA_SIM_THRESHOLD", sim_threshold))
        self.ttl_secs = ttl_secs
        self._client = httpx.Client(timeout=timeout_ms / 1000.0) if self.url else None
        self.enabled = self._handshake() if self._client else False

    # -- lifecycle -----------------------------------------------------------

    def _handshake(self) -> bool:
        """Best-effort ping so an unreachable Eunomia degrades to disabled cleanly."""
        try:
            # An unauthorized GET on a known-missing key returns 404 (auth ok) or
            # 401 (key wrong). Either proves the server is up; only network or
            # 5xx errors disable the cache.
            r = self._client.get(
                f"{self.url}/v1/memory/__handshake__",
                headers={"x-api-key": self.api_key},
            )
            return r.status_code in (200, 404)
        except (httpx.HTTPError, OSError):
            return False

    def close(self) -> None:
        if self._client is not None:
            self._client.close()

    # -- exact K/V ------------------------------------------------------------

    def get_exact(self, key: str) -> Any | None:
        """Return the cached *value* for ``key``, or ``None`` on miss / disabled."""
        if not self.enabled:
            return None
        try:
            r = self._client.get(
                f"{self.url}/v1/memory/{key}",
                headers={"x-api-key": self.api_key},
            )
            if r.status_code == 200:
                return r.json().get("value")
            return None
        except httpx.HTTPError:
            return None

    def store_exact(self, key: str, value: Any, tags: list[str] | None = None) -> None:
        """Persist a non-embedded entry. No-op when disabled or on transport error."""
        if not self.enabled:
            return
        body = {
            "id": key,
            "value": value,
            "ttl_secs": self.ttl_secs,
            "tags": tags or [],
        }
        try:
            self._client.post(
                f"{self.url}/v1/memory",
                headers={"x-api-key": self.api_key},
                json=body,
            )
        except httpx.HTTPError:
            pass

    # -- semantic recall ------------------------------------------------------

    def recall_semantic(
        self,
        embedding: list[float],
        *,
        min_k: int,
        tag: str | None = None,
    ) -> Any | None:
        """Return a cached value whose embedding is ≥ ``sim_threshold`` similar.

        Only returns a hit if the cached entry's stored ``k`` (a tag, e.g.
        ``"k=10"``) is at least ``min_k`` — otherwise the cached result is too
        small for the caller's request and counts as a miss.
        """
        if not self.enabled:
            return None
        body: dict[str, Any] = {"embedding": embedding, "k": 1}
        if tag is not None:
            body["filter"] = {"tags": [tag], "exclude_expired": True}
        try:
            r = self._client.post(
                f"{self.url}/v1/recall",
                headers={"x-api-key": self.api_key},
                json=body,
            )
            if r.status_code != 200:
                return None
            hits = r.json()
            if not hits:
                return None
            top = hits[0]
            if top.get("score", 0.0) < self.sim_threshold:
                return None
            # k-coverage check via the stored tag list.
            tags = top.get("entry", {}).get("metadata", {}).get("tags", [])
            cached_k = max(
                (int(t.split("=", 1)[1]) for t in tags if t.startswith("k=")),
                default=0,
            )
            if cached_k < min_k:
                return None
            return top["entry"]["value"]
        except (httpx.HTTPError, ValueError, KeyError):
            return None

    def store_semantic(
        self,
        key: str,
        embedding: list[float],
        value: Any,
        k: int,
        tag: str,
    ) -> None:
        """Persist a value keyed by both a unique string id and an embedding."""
        if not self.enabled:
            return
        body = {
            "id": key,
            "embedding": embedding,
            "value": value,
            "ttl_secs": self.ttl_secs,
            "tags": [tag, f"k={k}"],
        }
        try:
            self._client.post(
                f"{self.url}/v1/memory",
                headers={"x-api-key": self.api_key},
                json=body,
            )
        except httpx.HTTPError:
            pass


# ---------- module-level singletons ------------------------------------------


def from_env() -> tuple[EunomiaBridge, MetricsCollector]:
    """Build a bridge + metrics collector pair using environment configuration."""
    return EunomiaBridge(), MetricsCollector()
