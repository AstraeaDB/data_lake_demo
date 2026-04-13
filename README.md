# AstraeaDB Data Lake Demo

An end-to-end demonstration of how AstraeaDB can serve as an intelligent metadata catalog for a fragmented enterprise data lake, enabling an AI assistant to discover, correlate, and query data across disparate sources — even when the data spans different systems, file formats, time periods, and identifier schemes.

## Table of Contents

- [The Problem](#the-problem)
- [The Solution](#the-solution)
- [Architecture](#architecture)
- [Data Lake Contents](#data-lake-contents)
- [Metadata Graph](#metadata-graph)
- [Prerequisites](#prerequisites)
- [Quick Start with the Anthropic API](#quick-start-with-the-anthropic-api)
- [Quick Start with Ollama (qwen3:32b)](#quick-start-with-ollama-qwen332b)
- [Demo Modes](#demo-modes)
- [Using the AstraeaDB UI](#using-the-astraeadb-ui)
- [What Makes This Demo Significant](#what-makes-this-demo-significant)
- [From Demo to Production: A Real Data Lake with Spark](#from-demo-to-production-a-real-data-lake-with-spark)
- [Configuration Reference](#configuration-reference)
- [Development](#development)

---

## The Problem

Enterprises store massive amounts of data across dozens of systems in various formats. Over time, platforms are migrated — the company switches from Microsoft Teams to Zoom for video conferencing, or replaces a legacy HRIS with a modern HCM platform. The old data stays, but becomes disconnected. New employees don't know it exists. The formats differ. The column names differ. Even the identifiers for the same person differ across systems.

The result is a data lake that nobody can use. Not because the data isn't there, but because no one can find it.

A CEO asks: *"How has the number of video calls changed since the Pandemic?"* The analyst knows the data is somewhere in the lake — but which files? What format are they in? What are the column names? Are there multiple sources that need to be combined? The question is simple, but answering it requires institutional knowledge that may no longer exist.

## The Solution

AstraeaDB stores a semantic metadata graph that describes every data source in the lake, every field within each source, and the relationships between them. This graph includes:

- **Semantic embeddings** on every node, enabling natural-language search ("find data about video conferencing")
- **Temporal succession edges** that track platform migrations (Teams was succeeded by Zoom)
- **Overlap edges** that identify sources covering the same time period
- **Concept nodes** that link semantically equivalent fields across sources (`duration_minutes` in Teams and `length_minutes` in Zoom both map to a shared "Call Duration" concept)
- **Identity mapping edges** that connect different identifier formats for the same entity (`U0042` in security logs = `U0042@acmecorp.com` in email = `EMP-0042` in legacy HR = `WKR-0042` in modern HR)

An AI assistant uses this catalog as its "map" of the data lake. It searches the catalog to find relevant sources, reads the graph to understand field mappings and temporal relationships, and then queries the actual data files using DuckDB. The result: it can answer complex cross-domain questions that would otherwise require an analyst who happened to know where all the data was buried.

## Architecture

```
User Question
  │
  ▼
┌──────────────────────────────────────┐
│  LLM (Claude API or Ollama)          │
│  System prompt + 6 tool definitions  │
│  Multi-round tool calling loop       │
└──────┬────────────────┬──────────────┘
       │                │
       ▼                ▼
┌──────────────┐  ┌──────────────────────────┐
│  AstraeaDB   │  │  DuckDB                  │
│  (metadata)  │  │  (data lake query engine) │
│              │  │                          │
│  Semantic    │  │  CSV / JSON / JSONL /    │
│  search      │  │  Parquet — all queried   │
│              │  │  via standard SQL        │
│  Graph       │  │                          │
│  traversal   │  │  "SELECT ... FROM data"  │
└──────────────┘  └──────────────────────────┘

Tools available to the LLM:

  Metadata Discovery (AstraeaDB):
    search_catalog ─────── Semantic vector search across all metadata nodes
    get_source_details ─── Full schema, field descriptions, and types for a source
    find_related_sources ─ Follow SUCCEEDED_BY, OVERLAPS_WITH edges

  Data Querying (DuckDB):
    list_data_sources ──── Show all sources with row counts
    preview_data_source ── Column schema + sample rows
    query_data_source ──── Execute arbitrary SQL against any source
```

The LLM orchestrates the full pipeline: it discovers which data sources are relevant by searching the metadata catalog, reads the graph to understand schema differences and temporal context, writes SQL queries against the actual data files, and synthesizes a final answer citing its sources.

## Data Lake Contents

The demo simulates a realistic enterprise data lake across four business domains, eight data sources, three file formats, and a combined date range from 2017 to 2024.

| Source | Format | Domain | Rows | Time Range | Origin System |
|--------|--------|--------|------|------------|---------------|
| CERT Logon Events | CSV | Security | ~18K | Jan–Mar 2023 | Workstation auth monitoring |
| Web Proxy HTTP Access | JSONL | Security | ~25K | Jan–Mar 2023 | Web proxy / DLP gateway |
| Email Gateway Activity | Parquet | Security | ~15K | Jan–Mar 2023 | Email DLP / gateway |
| MS Teams Call Logs | CSV | Communications | ~23K | 2018–2021 | Microsoft Teams |
| Zoom Meeting Logs | JSON | Communications | ~77K | 2020–2024 | Zoom Video Communications |
| Legacy HRIS Records | CSV | HR | ~500 | 2017–2021 | Legacy on-prem HR system |
| Modern HCM Records | JSON | HR | ~2.2K | 2021–2024 | Cloud HCM platform |
| Project Tickets | Parquet | Project Mgmt | ~6.2K | 2019–2024 | Jira-style PM system |

All sources share a common universe of 200 synthetic employees distributed across 8 departments, with consistent cross-references using different identifier formats per system.

**Key relationships the demo exploits:**

- **Temporal succession:** Teams was replaced by Zoom (with a 15-month overlap during migration, March 2020 – June 2021). Legacy HR was replaced by Modern HCM (with a 6-month overlap, July – December 2021).
- **Multi-perspective:** The three security sources (logon, HTTP, email) all cover the same 90-day window and the same users, providing three independent views of employee activity.
- **Cross-domain identity:** User `U0042` in the security logs is `U0042@acmecorp.com` in communications and project management, `EMP-0042` in legacy HR, and `WKR-0042` in modern HR.

## Metadata Graph

The metadata graph loaded into AstraeaDB contains approximately 100 nodes and 160 edges:

| Node Type | Count | Description |
|-----------|-------|-------------|
| Domain | 4 | Security, Communications, HR, Project Management |
| DataSource | 8 | One per data file in the lake |
| Field | ~70 | Columns/fields across all sources |
| Concept | ~20 | Cross-cutting semantic concepts (User Identity, Call Duration, etc.) |

| Edge Type | Count | Purpose |
|-----------|-------|---------|
| BELONGS_TO_DOMAIN | 8 | Categorizes sources into domains |
| HAS_FIELD | ~70 | Links sources to their columns |
| MAPS_TO_CONCEPT | ~60 | Links fields to semantic concepts |
| SUCCEEDED_BY | 2 | Teams → Zoom, Legacy HR → Modern HCM |
| OVERLAPS_WITH | 5 | Sources covering the same time period |
| SAME_ENTITY_AS | ~12 | Identity mappings across ID formats |

Every node carries a 128-dimensional embedding vector generated from its description, enabling semantic search. These embeddings are generated via Ollama using the `embeddinggemma` model (768-dim raw output, Matryoshka-truncated to 128 dimensions, L2-normalized).

## Prerequisites

- **Python 3.10+**
- **AstraeaDB** built and available on PATH (or set `ASTRAEA_BIN` to point to the binary)
- **Ollama** (for embedding generation and optionally for local LLM inference)
- **One of:**
  - An Anthropic API key (for Claude), **or**
  - An Ollama-hosted chat model (for fully local inference)

### Optional

- **Astraea UI** — A Rust/Leptos web dashboard for visualizing the metadata graph in a browser. Requires Rust 1.75+, `cargo-leptos`, and Node.js 18+. See [Using the AstraeaDB UI](#using-the-astraeadb-ui) below.

---

## Quick Start with the Anthropic API

This path uses Claude via the Anthropic API for the chat model. Ollama is still used for embedding generation during setup.

### 1. Install dependencies

```bash
make deps
```

This installs the Python packages (`anthropic`, `duckdb`, `faker`, `pyarrow`, `pandas`, `httpx`, `pytest`) and the AstraeaDB Python client.

### 2. Set your API key

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

By default the demo uses `claude-sonnet-4-20250514`. To use a different model:

```bash
export ANTHROPIC_MODEL="claude-sonnet-4-20250514"  # or any other Claude model
```

### 3. Start Ollama and pull the embedding model

Ollama is needed during setup to generate the semantic embeddings that power AstraeaDB's vector search. If you don't have Ollama installed, see https://ollama.ai.

```bash
# In a separate terminal (or as a background service)
ollama serve

# Pull the embedding model
ollama pull embeddinggemma
```

### 4. Run the full setup pipeline

```bash
make setup
```

This runs four steps in sequence:

1. **`generate-data`** — Creates all 8 synthetic data files under `data/` (~167K total rows)
2. **`embeddings`** — Calls Ollama to generate 128-dim embedding vectors for every metadata node
3. **`ingest`** — Starts the AstraeaDB server and loads the full metadata graph (~100 nodes, ~160 edges, with embeddings)
4. **`validate`** — Runs the test suite to verify data integrity and metadata consistency

### 5. Run the demo

```bash
make demo
```

This starts AstraeaDB (if not already running) and launches the full demo: a narrated three-act walkthrough followed by an interactive chat session.

The `LLM_PROVIDER` defaults to `anthropic`, so the demo will use your Anthropic API key to call Claude.

---

## Quick Start with Ollama (qwen3:32b)

This path runs entirely locally with no external API calls. Ollama serves both the chat model (`qwen3:32b`) and the embedding model (`embeddinggemma`).

### 1. Install dependencies

```bash
make deps
```

### 2. Start Ollama and pull both models

```bash
# Start the Ollama server (if not already running)
ollama serve

# Pull the chat model (~20GB download)
ollama pull qwen3:32b

# Pull the embedding model
ollama pull embeddinggemma
```

**Hardware note:** `qwen3:32b` is a 32-billion parameter model. It requires a machine with at least 20GB of available RAM (or VRAM for GPU acceleration). Inference will be slower than the Anthropic API, especially on CPU-only machines. If your machine doesn't have the resources for this model, consider using a smaller model like `qwen3:8b` or `gemma3:12b`, though tool-calling quality may vary.

### 3. Run the full setup pipeline

```bash
make setup
```

Same as the Anthropic path: generates data, computes embeddings, loads the metadata graph into AstraeaDB, and validates everything.

### 4. Run the demo with Ollama as the LLM provider

```bash
LLM_PROVIDER=ollama OLLAMA_CHAT_MODEL=qwen3:32b make demo
```

This tells the orchestrator to use Ollama's `/api/chat` endpoint with `qwen3:32b` instead of the Anthropic API. The tool definitions are automatically converted from Anthropic format to OpenAI-compatible format for Ollama.

You can also set these as environment variables if you prefer:

```bash
export LLM_PROVIDER=ollama
export OLLAMA_CHAT_MODEL=qwen3:32b
make demo
```

### Setup without Ollama embeddings

If you don't have Ollama available at all (no embedding model, no chat model), you can still run the demo with the Anthropic API using pre-structured metadata lookups instead of semantic search:

```bash
make setup-no-embeddings
export ANTHROPIC_API_KEY="sk-ant-..."
make demo
```

The demo will still work — the LLM falls back to browsing all sources via `list_data_sources` and `preview_data_source` instead of using `search_catalog` for semantic discovery. The experience is slightly less impressive (the LLM has to manually scan all sources rather than jumping directly to the relevant ones), but the end results are the same.

---

## Demo Modes

```bash
make demo          # Full: narrated three-act walkthrough + interactive chat
make narrated      # Narrated walkthrough only (with presenter pauses)
make interactive   # Interactive chat only (skip the narration)
```

### The Narrated Walkthrough

The narrated mode runs through three acts, each demonstrating a different capability:

**Act 1: The Fragmented Lake** — Sets the scene. Displays the data lake contents as a directory tree, shows a timeline visualization of when each data source is active, and poses the motivating question: *"How has the number of video calls changed since the Pandemic?"*

**Act 2: The Intelligent Catalog** — Demonstrates two queries live:

1. *Temporal Succession:* "How has the number of video calls changed since the Pandemic? Show me monthly trends." — The LLM uses `search_catalog` to find Teams and Zoom, discovers via `find_related_sources` that Teams was succeeded by Zoom, queries both sources with appropriate SQL, and synthesizes a trend analysis that spans both platforms.

2. *Multi-Perspective Correlation:* "Show me all activity for user U0001 on January 2, 2023." — The LLM finds three independent security sources covering the same user and time period, queries each one, and presents a unified view of the user's logon, web browsing, and email activity.

**Act 3: Cross-Domain Intelligence** — The grand finale: *"What can you tell me about user U0001 across all of our systems?"* The LLM must span all four domains, discover that the same person appears as `U0001` (security), `U0001@acmecorp.com` (communications, PM), `EMP-0001` (legacy HR), and `WKR-0001` (modern HR), query each source, and assemble a comprehensive profile.

**Recap** — Summarizes the demo statistics (8 sources, 3 formats, 4 domains, 4 identifier formats bridged, 2 platform migrations tracked).

### Presenter Mode

For live presentations, use the `--interactive` flag (or `make narrated`) to pause between sections:

```bash
python3 -m src.orchestrator --mode narrated --interactive
```

Or set the environment variable:

```bash
INTERACTIVE=true make demo
```

### Interactive Chat

After the narrated walkthrough (or standalone with `make interactive`), you can ask your own questions. Some suggestions:

- "Which data sources contain information about the Engineering department?"
- "What happened on the day with the most security events?"
- "Compare employee meeting frequency before and after the pandemic"
- "Find users who appear in both security and HR data"
- "What was the average meeting duration on Zoom vs Teams?"

Type `/quit` to exit.

---

## Using the AstraeaDB UI

The [Astraea UI](../astraea-UI) is a Rust/WebAssembly dashboard that connects to the same AstraeaDB server the demo uses. Running it alongside the demo gives you a live visual window into the metadata graph — you can see the nodes and edges the LLM is querying in real time, explore the graph structure interactively, and run your own GQL queries.

### Starting the UI

You need three terminals:

```bash
# Terminal 1: AstraeaDB server (if not already running)
make start-astraea

# Terminal 2: Astraea UI
make ui
# This runs: cd /path/to/astraea-UI && cargo leptos serve
# First build takes a few minutes (compiling Rust to WebAssembly)

# Terminal 3: The demo itself
make demo
```

Once the UI compiles, open **http://localhost:3100** in your browser.

If AstraeaDB has authentication disabled (the default for local development), any API key will grant Admin access on the login screen.

### What to look at in the UI

**Query Console** (`/query`):

This is the most useful view during the demo. You can run GQL queries to see exactly what the LLM is seeing when it calls the metadata tools. Try these:

```gql
-- See all data sources
MATCH (s:DataSource) RETURN s

-- See the Teams → Zoom succession edge
MATCH (a:DataSource)-[e:SUCCEEDED_BY]->(b:DataSource) RETURN a, e, b

-- See all fields in a specific source
MATCH (s:DataSource {name: "Zoom Meeting Logs"})-[:HAS_FIELD]->(f:Field) RETURN f

-- See how fields map to shared concepts across sources
MATCH (f:Field)-[:MAPS_TO_CONCEPT]->(c:Concept {name: "Call Duration"}) RETURN f, c

-- See identity mappings
MATCH (a:Field)-[e:SAME_ENTITY_AS]->(b:Field) RETURN a, e, b

-- Graph statistics
-- Use the "Graph Stats" quick-action button
```

**Graph Explorer** (`/graph`):

Load the entire graph to see the full metadata structure visually. The graph is small enough (~100 nodes) that Cytoscape.js (Canvas mode) will be used automatically, giving you rich interactions:

- **Click a node** to see its properties and embedding vector
- **Filter by label** to isolate DataSource nodes, Field nodes, or Concept nodes
- **Filter by edge type** to see only SUCCEEDED_BY edges (platform migrations), MAPS_TO_CONCEPT edges (semantic links), or SAME_ENTITY_AS edges (identity mappings)
- **Use layouts** — "Force" gives a natural clustering; "Concentric" arranges by connectivity
- **Export** the visualization as a PNG or the graph data as JSON

**Admin Panel** (`/admin`):

Shows server status, graph metrics (node count, edge count, index statistics), and the server configuration. Useful for verifying that the metadata was ingested correctly.

### UI alongside the demo

The most compelling way to use the UI during a presentation is to have it open on a second monitor (or a split screen) with the Graph Explorer showing the full metadata graph. As the demo narrates the three acts, you can highlight the relevant parts of the graph:

- During **Act 1**, show the full graph to visualize the fragmentation — 8 DataSource nodes scattered across 4 Domain clusters, with 70+ Field nodes hanging off each source.
- During **Act 2 Question 1**, filter to show SUCCEEDED_BY edges to highlight the Teams → Zoom migration path. Then filter to MAPS_TO_CONCEPT to show how `duration_minutes` and `length_minutes` both connect to the "Call Duration" concept.
- During **Act 2 Question 2**, filter to OVERLAPS_WITH to show the three security sources covering the same time window.
- During **Act 3**, filter to SAME_ENTITY_AS to show the identity mapping edges that let the LLM connect `U0001` across all four domains.

---

## What Makes This Demo Significant

### The core insight

The data lake problem is not a storage problem — it's a knowledge problem. Every enterprise has the data. What they lack is a way to know what data exists, what it means, and how it connects to other data. Traditional data catalogs solve this with manual tagging and rigid schemas. AstraeaDB solves it with a knowledge graph that an AI can navigate.

### What this demo proves

1. **Semantic discovery works.** When the LLM searches for "video conferencing data," AstraeaDB's vector search returns Teams and Zoom sources ranked by embedding similarity — even though neither source has "video conferencing" in its name. The LLM doesn't need to know what's in the lake; it just describes what it's looking for.

2. **Graph relationships encode institutional knowledge.** The SUCCEEDED_BY edge between Teams and Zoom captures knowledge that would otherwise exist only in the heads of employees who were there during the migration. The MAPS_TO_CONCEPT edges that link `duration_minutes` to `length_minutes` via a shared "Call Duration" concept encode the fact that these are the same metric in different schemas. This knowledge survives employee turnover.

3. **Identity resolution across systems is tractable.** The SAME_ENTITY_AS edges and the identifier format documentation in the system prompt enable the LLM to correlate user `U0042` in security logs with `EMP-0042` in HR records — something that would normally require a human analyst who knows the naming conventions of both systems.

4. **Multi-format querying is a solved problem.** DuckDB reads CSV, JSON, JSONL, and Parquet files through a uniform SQL interface. The LLM writes SQL without needing to know the underlying format. This is the "query engine" layer — in production, this would be Spark, Trino, or another lake query engine.

5. **The AI is the interface, not the intelligence.** AstraeaDB is the intelligence. Without the metadata graph, the LLM would have to read and understand every data source in the lake — an approach that doesn't scale. With the graph, the LLM can find the right data in seconds, understand the schema, and write the right queries. The graph is the map; the LLM is the navigator.

---

## From Demo to Production: A Real Data Lake with Spark

This demo uses DuckDB to query flat files on disk. In a real enterprise deployment, the architecture would scale in several ways:

### What stays the same

- **AstraeaDB as the metadata catalog.** The graph schema (Domains, DataSources, Fields, Concepts, and their relationships) is production-ready. The same node and edge types would describe real data sources in a real lake. AstraeaDB would run as a persistent service, updated via CI/CD whenever new data sources are onboarded or schemas change.

- **The LLM tool-calling pattern.** The six tools (`search_catalog`, `get_source_details`, `find_related_sources`, `list_data_sources`, `preview_data_source`, `query_data_source`) represent a generalizable interface. In production, these would be MCP tools or API endpoints rather than in-process function calls, but the LLM interaction pattern is identical.

- **Semantic embeddings on metadata.** The approach of embedding source and field descriptions and using vector search for discovery scales to thousands of data sources. AstraeaDB's hybrid search (combining graph proximity with vector similarity) becomes more valuable as the graph grows, because it can prioritize sources that are both semantically relevant and structurally connected to sources the user has already asked about.

### What changes at scale

- **DuckDB → Apache Spark / Trino / Databricks SQL.** Instead of DuckDB reading local files, the `query_data_source` tool would submit SQL to a distributed query engine. Spark can read from S3, ADLS, GCS, Delta Lake, Iceberg tables, and Hive metastores. The tool interface stays the same — the LLM still writes SQL and gets rows back — but the backend can now handle terabytes.

- **Flat files → Delta Lake / Iceberg tables.** Real data lakes use table formats that support ACID transactions, schema evolution, time travel, and partition pruning. The metadata in AstraeaDB would include partition keys, table format version, and storage location so the LLM can write efficient queries.

- **200 users → millions of entities.** The identity resolution problem becomes harder but more valuable. AstraeaDB's graph would include a richer identity subgraph, potentially powered by automated entity resolution, linking user IDs, email addresses, SSO principals, and employee IDs across hundreds of systems.

- **8 sources → hundreds or thousands.** This is where AstraeaDB's semantic search becomes critical. No human can remember the schemas of 500 data sources. But AstraeaDB can store and search embeddings for all of them, and the LLM can narrow down to the 3-4 relevant sources in a single vector search call.

- **Manual metadata curation → automated ingestion.** In production, metadata would be extracted from schema registries (Confluent, AWS Glue, Hive Metastore), data catalogs (Unity Catalog, Alation, DataHub), and even from the data itself via LLM-generated descriptions. AstraeaDB would be populated by pipelines, not scripts.

- **Single-user demo → multi-tenant service.** The chatbot would be exposed as an internal tool (Slack bot, web app, API) with access controls. AstraeaDB's role-based authentication would enforce data source visibility — an analyst in Finance might not see HR data sources in their search results.

### The business case

An enterprise with 500 data sources in its lake has a discovery problem that costs real money: analysts spend hours searching for data, build pipelines to the wrong source, or simply give up and re-collect data that already exists. AstraeaDB turns the data lake from a dumping ground into a searchable, navigable knowledge base — and the LLM turns that knowledge base into a conversational interface that any employee can use.

---

## Configuration Reference

All settings can be overridden via environment variables.

| Variable | Default | Description |
|----------|---------|-------------|
| `ASTRAEA_HOST` | `127.0.0.1` | AstraeaDB server host |
| `ASTRAEA_PORT` | `7687` | AstraeaDB server port |
| `ASTRAEA_BIN` | `astraeadb` | Path to AstraeaDB binary |
| `LLM_PROVIDER` | `anthropic` | LLM backend: `anthropic` or `ollama` |
| `ANTHROPIC_API_KEY` | — | Required when `LLM_PROVIDER=anthropic` |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | Claude model identifier |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_CHAT_MODEL` | `gemma3:12b` | Ollama model for chat (override with `qwen3:32b`) |
| `EMBEDDING_MODEL` | `embeddinggemma` | Ollama model for embeddings |
| `INTERACTIVE` | `false` | Pause between demo sections for presenter control |

---

## Development

```bash
make test          # Run the full test suite (requires AstraeaDB running)
make test-quick    # Run tests that don't require AstraeaDB
make clean         # Remove all generated data files
make setup         # Regenerate everything from scratch
make help          # Show all available Makefile targets
```

### Project structure

```
├── config.py                  # Central configuration (paths, env vars, constants)
├── Makefile                   # Build/run automation
├── requirements.txt           # Python dependencies
│
├── data/                      # Generated data lake files (8 sources, 4 domains)
│   ├── security/              # CSV, JSONL, Parquet
│   ├── communications/        # CSV, JSON
│   ├── hr/                    # CSV, JSON
│   └── projects/              # Parquet
│
├── metadata/                  # Graph metadata definitions
│   ├── domains.json           # 4 Domain nodes
│   ├── sources.json           # 8 DataSource nodes
│   ├── fields.json            # ~70 Field nodes
│   ├── concepts.json          # ~20 Concept nodes
│   ├── edges.json             # ~160 edges (all relationship types)
│   ├── embeddings.json        # Pre-computed 128-dim embeddings (generated)
│   └── id_map.json            # String IDs → AstraeaDB node IDs (generated)
│
├── scripts/
│   ├── generate_data.py       # Create all synthetic data files
│   ├── generate_embeddings.py # Compute embeddings via Ollama
│   └── ingest_metadata.py     # Load graph into AstraeaDB server
│
├── src/
│   ├── orchestrator.py        # Main demo controller (LLM + tools + narration)
│   ├── mcp_bridge.py          # AstraeaDB client (DirectBridge + McpBridge)
│   ├── duckdb_tools.py        # DuckDB query engine (SQL over any file format)
│   ├── embeddings.py          # Embedding generation via Ollama
│   └── display.py             # Console formatting (banners, tables, timelines)
│
├── test_demo.py               # pytest suite (data, metadata, DuckDB, end-to-end)
└── schema.md                  # Metadata graph schema documentation
```
