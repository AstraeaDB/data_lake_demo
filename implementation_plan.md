# Data Lake Demo: Implementation Plan

## Executive Summary

This demo shows how **AstraeaDB** can serve as an intelligent metadata catalog for a fragmented enterprise data lake, enabling an LLM-powered chatbot to discover, correlate, and query data across disparate sources — even when the user doesn't know what data exists or where to find it.

**Target audience:** A storage solutions company serving cloud providers, demonstrating that storage can be "intelligent" — helping customers find and use data they didn't even realize they were keeping.

**Demo format:** Hybrid narrated walkthrough + interactive chat, designed for live presentation.

**Architecture:** AstraeaDB (server mode, port 7687) stores the metadata graph. Data files live on disk in CSV, JSON, and Parquet formats. DuckDB provides unified SQL querying across all formats. The LLM (configurable: Claude API default, Ollama fallback) discovers data via AstraeaDB MCP tools, then queries it via DuckDB tools.

---

## 1. Project Structure

```
data_lake_demo/
├── CLAUDE.md                          # Project instructions
├── Makefile                           # Setup and run targets
├── README.md                          # Project documentation
├── requirements.txt                   # Python dependencies
├── config.py                          # Configuration (ports, API keys, paths, LLM provider)
│
├── data/                              # The simulated "data lake"
│   ├── security/
│   │   ├── logon_events.csv           # CERT-based logon/logoff (CSV)
│   │   ├── http_access.jsonl          # CERT-based HTTP browsing (JSONL)
│   │   └── email_activity.parquet     # CERT-based email records (Parquet)
│   ├── communications/
│   │   ├── teams_calls_2018_2021.csv  # MS Teams call logs (CSV)
│   │   └── zoom_meetings_2020_2024.json # Zoom meeting logs (JSON)
│   ├── hr/
│   │   ├── legacy_hris_2017_2021.csv  # Legacy HR system (CSV)
│   │   └── modern_hcm_2021_2024.json  # Modern HCM platform (JSON)
│   └── projects/
│       └── project_tickets.parquet    # Jira-style tickets (Parquet)
│
├── metadata/                          # Graph metadata definitions
│   ├── sources.json                   # DataSource node definitions
│   ├── fields.json                    # Field node definitions (with Avro-like type info)
│   ├── concepts.json                  # Concept node definitions
│   ├── domains.json                   # Domain node definitions
│   └── edges.json                     # All edge definitions
│
├── scripts/
│   ├── download_cert.py               # Download CERT Insider Threat dataset
│   ├── generate_data.py               # Generate all synthetic + CERT-derived data
│   ├── generate_embeddings.py         # Embed all metadata descriptions via Ollama
│   ├── ingest_metadata.py             # Load metadata graph into AstraeaDB
│   └── validate.py                    # Validate data files and metadata consistency
│
├── src/
│   ├── __init__.py
│   ├── orchestrator.py                # Main demo orchestrator (narrated + interactive)
│   ├── mcp_bridge.py                  # AstraeaDB MCP client (reuse pattern from GraphRAG demo)
│   ├── duckdb_tools.py                # DuckDB-backed data lake query tools
│   ├── embeddings.py                  # Embedding generation (Ollama embeddinggemma)
│   ├── narrator.py                    # Scripted narration for Act 1-3
│   └── display.py                     # Formatted console output (tables, banners, etc.)
│
├── test_demo.py                       # Test suite
│
├── voiceover.md                       # Narrator script for presentations
└── schema.md                          # Graph schema documentation
```

---

## 2. Data Sources (8 Sources, 4 Domains)

### 2.1 Security Domain — CERT Insider Threat Data (Multi-Perspective)

The CERT Insider Threat Test Dataset (CMU/DARPA) provides real-format enterprise user activity logs for 1,000 synthetic users over 500 days. We'll extract a subset and split it across three files in different formats.

**Source 1: `logon_events.csv`** (CSV)
- Derived from CERT `logon.csv`
- ~10,000–20,000 rows
- Columns: `user_id`, `timestamp`, `computer`, `activity` (Logon/Logoff), `auth_method`
- Represents: the authentication/access control system
- Time coverage: full date range of the CERT subset

**Source 2: `http_access.jsonl`** (JSONL)
- Derived from CERT `http.csv`
- ~15,000–30,000 rows
- Fields: `user_id`, `timestamp`, `url`, `hostname`, `content_type`, `bytes_transferred`
- Represents: the web proxy / content filter
- Time coverage: full date range

**Source 3: `email_activity.parquet`** (Parquet)
- Derived from CERT `email.csv`
- ~10,000–20,000 rows
- Columns: `user_id`, `timestamp`, `to_addresses`, `cc_addresses`, `bcc_addresses`, `from_address`, `size_bytes`, `has_attachments`, `attachment_count`
- Represents: the email gateway / DLP system
- Time coverage: full date range

**Multi-perspective link:** All three sources share `user_id` (e.g., `U1234`) and `timestamp`, representing different views of the same user's activity at the same time.

### 2.2 Communications Domain — Temporal Succession

**Source 4: `teams_calls_2018_2021.csv`** (CSV)
- Synthetic, generated with Faker
- ~8,000–12,000 rows
- Columns: `call_id`, `call_date`, `organizer_email`, `duration_minutes`, `participant_count`, `call_type` (audio/video/screen_share), `department`
- Time coverage: 2018-01-01 to 2021-06-30
- User IDs: derived from CERT user set (mapped to emails like `U1234@acmecorp.com`)

**Source 5: `zoom_meetings_2020_2024.json`** (JSON array)
- Synthetic, generated with Faker
- ~10,000–15,000 rows
- Fields: `meeting_id`, `meeting_start` (ISO 8601), `host` (email), `length_minutes`, `attendees` (array of emails), `meeting_type` (instant/scheduled/recurring), `recording_available` (bool), `org_unit`
- Time coverage: 2020-03-01 to 2024-12-31
- Overlap period with Teams: 2020-03 to 2021-06 (both systems active during migration)

**Temporal succession link:** Both describe video conferencing, but with different schemas, column names, and time ranges. The overlap period (2020-03 to 2021-06) is when both platforms were active during the migration.

### 2.3 HR Domain — Temporal Succession

**Source 6: `legacy_hris_2017_2021.csv`** (CSV)
- Hybrid: IBM HR Analytics schema with synthetic connected content
- ~2,000–3,000 rows (employee records, one row per employee per year)
- Columns: `employee_id`, `name`, `department`, `job_role`, `hire_date`, `termination_date`, `salary`, `performance_rating` (1-5), `years_at_company`, `overtime_flag`, `snapshot_date`
- Time coverage: 2017-01-01 to 2021-12-31
- User IDs: mapped to CERT user set (e.g., `employee_id` corresponds to `user_id` in security data — but with a different format like `EMP-1234` vs `U1234`)

**Source 7: `modern_hcm_2021_2024.json`** (JSON array)
- Synthetic, generated with Faker
- ~2,500–4,000 rows
- Fields: `worker_id`, `full_name`, `business_unit`, `position_title`, `start_date` (ISO 8601), `end_date`, `base_compensation`, `performance_score` (0.0-5.0), `engagement_index`, `skills` (array), `manager_worker_id`, `learning_completions`, `effective_date`
- Time coverage: 2021-07-01 to 2024-12-31
- Overlap period with legacy: 2021-07 to 2021-12 (migration cutover)

**Temporal succession link:** Both describe employees, but the legacy system uses `employee_id` / `performance_rating` (integer 1-5) while the modern system uses `worker_id` / `performance_score` (float 0.0-5.0). The LLM must understand these are the same concept in different scales.

### 2.4 Project Management Domain

**Source 8: `project_tickets.parquet`** (Parquet)
- Synthetic, modeled after Jira schema
- ~5,000–8,000 rows
- Columns: `ticket_key` (e.g., `ENG-1234`), `summary`, `description`, `status` (Open/In Progress/Done/Closed), `priority` (Critical/High/Medium/Low), `assignee_email`, `reporter_email`, `project`, `sprint`, `created_date`, `resolved_date`, `story_points`, `labels` (array), `components` (array)
- Time coverage: 2019-01-01 to 2024-12-31
- User IDs: assignee/reporter emails match communications email format (`U1234@acmecorp.com`)

**Cross-domain link:** Assignee emails connect to communications data and (via the email↔employee mapping) to HR data.

### 2.5 Format Summary

| # | Source | Format | Domain | Rows | Time Range | ID Format |
|---|--------|--------|--------|------|------------|-----------|
| 1 | logon_events.csv | CSV | Security | 10K-20K | CERT range | `U1234` |
| 2 | http_access.jsonl | JSONL | Security | 15K-30K | CERT range | `U1234` |
| 3 | email_activity.parquet | Parquet | Security | 10K-20K | CERT range | `U1234` |
| 4 | teams_calls_2018_2021.csv | CSV | Comms | 8K-12K | 2018–2021 | `U1234@acmecorp.com` |
| 5 | zoom_meetings_2020_2024.json | JSON | Comms | 10K-15K | 2020–2024 | `U1234@acmecorp.com` |
| 6 | legacy_hris_2017_2021.csv | CSV | HR | 2K-3K | 2017–2021 | `EMP-1234` |
| 7 | modern_hcm_2021_2024.json | JSON | HR | 2.5K-4K | 2021–2024 | `WKR-1234` |
| 8 | project_tickets.parquet | Parquet | PM | 5K-8K | 2019–2024 | `U1234@acmecorp.com` |

**Identifier bridging:** The graph metadata will contain `SAME_ENTITY_AS` edges connecting the user ID fields across sources:
- `U1234` (security) ↔ `U1234@acmecorp.com` (comms/PM) — pattern-based (append domain)
- `U1234` (security) ↔ `EMP-1234` (legacy HR) — mapping table (numeric portion matches)
- `EMP-1234` (legacy HR) ↔ `WKR-1234` (modern HR) — mapping table (migration crosswalk)

Some of these are discoverable by pattern (the LLM can infer the email from the user ID). Others require the graph metadata to explicitly connect them — demonstrating the value of semantic bridging.

---

## 3. AstraeaDB Metadata Graph Schema

### 3.1 Node Types

**DataSource** (8 nodes)
```json
{
  "labels": ["DataSource"],
  "properties": {
    "name": "CERT Logon Events",
    "description": "Authentication and session activity logs from the enterprise identity management system. Records user logon and logoff events across workstations, including timestamps, target computers, and authentication methods. Useful for analyzing access patterns, working hours, and detecting anomalous login behavior.",
    "format": "csv",
    "file_path": "data/security/logon_events.csv",
    "origin_system": "Enterprise Identity Management",
    "active_from": "2010-01-02",
    "active_to": "2011-05-16",
    "row_count": 15000,
    "delimiter": ",",
    "has_header": true
  },
  "embedding": [/* 128-dim vector from description */]
}
```

**Field** (~60-80 nodes, one per column/field across all 8 sources)
```json
{
  "labels": ["Field"],
  "properties": {
    "name": "duration_minutes",
    "description": "Length of the video or audio call in minutes, measured from the time the first participant joins to the time the last participant leaves.",
    "data_type": "int",
    "nullable": false,
    "avro_type": {"type": "int"},
    "sample_values": ["15", "30", "45", "62", "8"],
    "source_name": "MS Teams Call Logs"
  },
  "embedding": [/* 128-dim vector from description */]
}
```

**Concept** (~15-25 nodes)
```json
{
  "labels": ["Concept"],
  "properties": {
    "name": "Call Duration",
    "description": "The length of time a video or audio call lasted. May be measured in minutes or seconds depending on the source system. Represents wall-clock time from start to end of the communication session.",
    "domain": "Communications"
  },
  "embedding": [/* 128-dim vector from description */]
}
```

Example concepts:
- **Security:** User Identity, Authentication Event, Session Activity, Web Browsing Activity, Email Communication, Timestamp
- **Communications:** Call Duration, Meeting Size, Meeting Organizer, Call Type, Meeting Schedule
- **HR:** Employee Identity, Department/Business Unit, Job Title/Position, Compensation, Performance Rating, Employment Period, Employee Skills
- **PM:** Ticket/Issue, Ticket Status, Priority Level, Assignee, Sprint/Iteration, Story Points
- **Cross-cutting:** Person/User, Time Period, Organizational Unit

**Domain** (4 nodes)
```json
{
  "labels": ["Domain"],
  "properties": {
    "name": "Security",
    "description": "Data related to cybersecurity, authentication, access control, network monitoring, and threat detection. Includes logs from identity management systems, web proxies, email gateways, firewalls, and intrusion detection systems."
  },
  "embedding": [/* 128-dim vector from description */]
}
```

### 3.2 Edge Types

| Edge Type | From → To | Count (est.) | Properties | Temporal |
|-----------|-----------|--------------|------------|----------|
| `HAS_FIELD` | DataSource → Field | ~60-80 | `ordinal_position` (column order) | No |
| `MAPS_TO_CONCEPT` | Field → Concept | ~60-80 | `mapping_notes` (optional) | No |
| `SUCCEEDED_BY` | DataSource → DataSource | 2 | `migration_date`, `overlap_start`, `overlap_end` | Yes |
| `OVERLAPS_WITH` | DataSource → DataSource | 3 | `overlap_reason` (same_event / migration) | No |
| `BELONGS_TO_DOMAIN` | DataSource → Domain | 8 | — | No |
| `RELATES_TO` | Concept → Concept | ~10-15 | `relationship` (equivalent/broader/narrower) | No |
| `SAME_ENTITY_AS` | Field → Field | ~8-12 | `mapping_type` (pattern/crosswalk/semantic), `transform` | No |

**Total estimated graph size:** ~100-120 nodes, ~160-200 edges

### 3.3 Temporal Edges

The `SUCCEEDED_BY` edges carry temporal validity intervals:
```json
{
  "source": "teams_calls_node_id",
  "target": "zoom_meetings_node_id",
  "edge_type": "SUCCEEDED_BY",
  "properties": {
    "migration_date": "2021-07-01",
    "overlap_start": "2020-03-01",
    "overlap_end": "2021-06-30"
  },
  "valid_from": 1583020800000,
  "valid_to": 1625097600000
}
```

This enables temporal queries like: "What communication data sources were active in 2020?" → returns both Teams and Zoom (overlap period).

---

## 4. Data Generation Pipeline

### 4.1 Step 1: Download CERT Data (`scripts/download_cert.py`)

```
Download CERT Insider Threat Test Dataset r4.2 from CMU
→ Extract logon.csv, http.csv, email.csv
→ Store in data/cert_raw/
```

CERT data uses relative timestamps (integer seconds from epoch). We'll keep these as-is for the security data — they represent a 500-day window that we'll document as the "monitoring period."

**Subset strategy:**
- Select ~200 users (from the 1,000 total) to keep the graph manageable
- Include all users flagged in the insider threat scenarios (for interesting query results)
- Include a random sample of benign users
- Cap rows per source at the target volumes (10K-30K)

### 4.2 Step 2: Generate Synthetic Data (`scripts/generate_data.py`)

This script generates the non-CERT data sources using Python's Faker library, seeded for reproducibility.

**User universe:** Establish a set of ~200 synthetic employees that appear across all sources:
```python
# Master user registry (not stored in the lake — this IS the fragmentation)
users = [
    {
        "cert_id": "U1234",
        "email": "U1234@acmecorp.com",
        "legacy_emp_id": "EMP-1234",
        "modern_worker_id": "WKR-1234",
        "name": "Jane Smith",
        "department": "Engineering",
        "hire_date": "2017-03-15",
        "termination_date": None
    },
    ...
]
```

The key insight: this mapping is what the LLM has to discover. Some connections are inferrable (U1234 → U1234@acmecorp.com), others require the metadata graph (EMP-1234 → WKR-1234).

**Generation rules per source:**

| Source | Generator Logic |
|--------|----------------|
| Teams calls | Random calls 2018-2021, heavier in 2019-2020 (pre-pandemic normal), sharp increase in March 2020 |
| Zoom meetings | Start March 2020, ramp up through 2020, stabilize 2021+, Teams-era users migrate over |
| Legacy HRIS | Annual snapshots for each employee, realistic salary progression, some terminations |
| Modern HCM | Quarterly records from July 2021, richer fields, same employees migrated over |
| Project tickets | Continuous ticket creation 2019-2024, assigned to employees, realistic status progression |

**Realistic patterns to embed:**
- Video call volume spikes dramatically in March 2020 (pandemic)
- Some employees visible in security logs show unusual patterns (CERT insider threat scenarios)
- Employee attrition correlates with certain departments
- Project velocity varies by quarter and team

### 4.3 Step 3: Generate Embeddings (`scripts/generate_embeddings.py`)

Following the GraphRAG demo pattern:
- Use Ollama's `embeddinggemma` model
- Generate 768-dim embeddings for each node's description text
- Apply Matryoshka truncation to 128 dimensions
- L2-normalize the truncated vectors

**What gets embedded:**
- Each DataSource node: embed the `description` property
- Each Field node: embed the `description` property
- Each Concept node: embed the `description` property
- Each Domain node: embed the `description` property

### 4.4 Step 4: Ingest Metadata (`scripts/ingest_metadata.py`)

Connect to AstraeaDB server (JSON-TCP, port 7687) and:
1. Create all Domain nodes (4)
2. Create all Concept nodes (~20)
3. Create all DataSource nodes (8) with embeddings
4. Create all Field nodes (~70) with embeddings
5. Create all edges (~180)
6. Verify graph integrity (all edges reference valid nodes)
7. Print graph statistics

### 4.5 Step 5: Validate (`scripts/validate.py`)

- Verify all 8 data files exist and are readable
- Verify row counts match metadata
- Verify field names in actual files match Field nodes in graph
- Verify AstraeaDB is running and graph is loaded
- Verify embedding dimensions are correct (128)
- Run a sample vector search to confirm HNSW index is working

---

## 5. MCP Tool Design

### 5.1 AstraeaDB MCP Tools (Metadata Discovery)

These are AstraeaDB's built-in MCP tools, exposed when AstraeaDB runs in MCP proxy mode connected to the server. The orchestrator uses these for metadata discovery:

| Tool | Purpose in Demo |
|------|-----------------|
| `find_by_label("DataSource")` | List all data sources in the lake |
| `find_by_label("Concept")` | List all known business concepts |
| `find_by_label("Domain")` | List all data domains |
| `get_node(id)` | Get full details of a source (format, path, time range, description) |
| `neighbors(id, direction)` | Explore: source → fields, field → concepts, source → domain |
| `vector_search(query_vec, k)` | "Find data about video conferencing" → semantically similar sources/fields |
| `hybrid_search(anchor, query_vec, k, alpha)` | Find sources both semantically relevant AND structurally connected |
| `query(gql)` | Structured queries: "MATCH (s:DataSource) WHERE s.active_from <= '2020-06-01' AND s.active_to >= '2020-06-01' RETURN s" |

### 5.2 Data Lake Query Tools (Custom DuckDB-Based)

These are custom MCP tools provided by the demo application for reading the actual data files. All are backed by DuckDB, which natively reads CSV, JSON, and Parquet.

**Tool: `query_data_source`**
```
Parameters:
  - source_name: str     # Name of the data source (matches DataSource node name)
  - sql: str             # SQL query to execute against the source
  - limit: int = 100     # Max rows to return

Returns: JSON array of result rows

Example:
  query_data_source(
    source_name="MS Teams Call Logs",
    sql="SELECT call_date, COUNT(*) as call_count FROM data GROUP BY call_date ORDER BY call_date",
    limit=50
  )
```

The tool resolves `source_name` to a file path using AstraeaDB metadata, then executes the SQL via DuckDB. DuckDB handles format detection automatically:
```python
# Pseudocode
def query_data_source(source_name, sql, limit=100):
    # Look up file path and format from AstraeaDB metadata
    source_info = get_source_info(source_name)  # {path, format}

    conn = duckdb.connect()

    # DuckDB reads any format transparently
    if source_info["format"] == "csv":
        conn.execute(f"CREATE VIEW data AS SELECT * FROM read_csv_auto('{source_info['path']}')")
    elif source_info["format"] in ("json", "jsonl"):
        conn.execute(f"CREATE VIEW data AS SELECT * FROM read_json_auto('{source_info['path']}')")
    elif source_info["format"] == "parquet":
        conn.execute(f"CREATE VIEW data AS SELECT * FROM read_parquet('{source_info['path']}')")

    result = conn.execute(f"{sql} LIMIT {limit}").fetchdf()
    return result.to_dict(orient="records")
```

**Tool: `preview_data_source`**
```
Parameters:
  - source_name: str     # Name of the data source
  - n_rows: int = 5      # Number of sample rows

Returns: First N rows + column names/types

Purpose: Let the LLM quickly inspect a source's actual content and structure
```

**Tool: `list_data_sources`**
```
Parameters: none

Returns: Summary table of all known data sources (name, format, domain, time range, row count)

Purpose: Quick orientation — what's in the lake?
```

### 5.3 Tool Registration

The custom DuckDB tools will be registered as additional MCP tools alongside AstraeaDB's built-in tools. The orchestrator manages both tool sets.

**Implementation approach:** Follow the GraphRAG demo's `mcp_bridge.py` pattern — launch AstraeaDB MCP as a subprocess, communicate via JSON-RPC 2.0 over stdio. Add the custom DuckDB tools as locally-handled tools in the orchestrator (not routed through MCP).

---

## 6. LLM Integration

### 6.1 Configurable Provider

```python
# config.py
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")  # "anthropic" or "ollama"
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Ollama
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:12b")
```

Default to Claude (Anthropic API) for best results. Ollama fallback for offline/cost-free demos.

### 6.2 System Prompt

The system prompt tells the LLM it is a data analyst assistant with access to:
1. A metadata catalog (AstraeaDB) that knows what data sources exist, their schemas, time ranges, and semantic relationships
2. Data query tools (DuckDB) that can read and query the actual data files

The prompt instructs the LLM to:
1. **Always start with discovery** — search the catalog before trying to read data
2. **Explain its reasoning** — narrate which sources it found and why it chose them
3. **Handle schema differences** — when sources use different column names for the same concept, explain the mapping
4. **Synthesize across sources** — combine results from multiple sources into a coherent answer
5. **Cite sources** — always name which data sources contributed to the answer

### 6.3 Tool-Calling Loop

Following the GraphRAG demo's multi-round pattern:

```
User question
  → LLM decides which catalog tools to call (AstraeaDB MCP)
  → Orchestrator executes catalog queries, returns results
  → LLM analyzes metadata, decides which data to query
  → LLM formulates SQL queries via DuckDB tools
  → Orchestrator executes data queries, returns results
  → LLM may iterate (query more sources, refine queries)
  → LLM synthesizes final answer
```

Max rounds: 8 (more than GraphRAG's 5, because this demo requires both discovery AND query steps).

---

## 7. Demo Orchestrator Architecture

### 7.1 Module: `src/orchestrator.py`

The orchestrator manages the full demo flow: narrated walkthrough followed by interactive chat.

```python
class DemoOrchestrator:
    def __init__(self, config):
        self.mcp = McpBridge(config)       # AstraeaDB MCP connection
        self.duckdb = DuckDbTools(config)   # Data lake query tools
        self.llm = LlmClient(config)       # Claude or Ollama
        self.embedder = Embedder(config)    # Ollama embeddinggemma
        self.narrator = Narrator()          # Scripted narration

    def run_narrated_demo(self):
        """Three-act scripted walkthrough."""
        self.act1_fragmented_lake()
        self.act2_intelligent_catalog()
        self.act3_cross_domain()
        self.recap()

    def run_interactive(self):
        """Open-ended chat after narrated portion."""
        while True:
            question = input("\n> ")
            if question in ("/quit", "/exit"):
                break
            answer = self.query(question)
            print(answer)

    def query(self, question):
        """Full discovery → query → synthesis pipeline."""
        # 1. Embed the question
        query_vec = self.embedder.embed(question)
        # 2. Multi-round tool-calling loop
        messages = [system_prompt, user_message(question)]
        for round in range(MAX_ROUNDS):
            response = self.llm.chat(messages, tools=all_tools)
            if response.has_tool_calls():
                results = self.execute_tools(response.tool_calls)
                messages.append(tool_results(results))
            else:
                return response.text
        return response.text  # Final answer after max rounds

    def run(self):
        """Main entry point: narrated demo then interactive."""
        self.run_narrated_demo()
        print("\n--- Interactive Mode ---")
        print("Ask any question about the data lake. Type /quit to exit.\n")
        self.run_interactive()
```

### 7.2 Module: `src/narrator.py`

Handles scripted narration with optional interactive pauses:

```python
class Narrator:
    def banner(self, text):
        """Display a section banner."""

    def narrate(self, text):
        """Print narrator text with styling."""

    def pause(self, prompt="Press Enter to continue..."):
        """Pause for presenter (--interactive flag)."""

    def show_table(self, headers, rows):
        """Display formatted data table."""

    def show_sources(self, sources):
        """Display data lake contents as a visual directory listing."""
```

### 7.3 Module: `src/duckdb_tools.py`

```python
class DuckDbTools:
    def __init__(self, config):
        self.conn = duckdb.connect()
        self.source_registry = {}  # name → {path, format}

    def register_source(self, name, path, format):
        """Register a data source for querying."""

    def query(self, source_name, sql, limit=100):
        """Execute SQL against a named source."""

    def preview(self, source_name, n_rows=5):
        """Return first N rows with schema info."""

    def list_sources(self):
        """Return summary of all registered sources."""
```

### 7.4 Module: `src/mcp_bridge.py`

Reuse the pattern from the GraphRAG demo:
- Launch AstraeaDB MCP server as subprocess (`astraeadb mcp --address 127.0.0.1:7687`)
- Communicate via JSON-RPC 2.0 over stdin/stdout
- Enrich results with human-readable names/descriptions
- Handle connection lifecycle (startup, health check, shutdown)

---

## 8. Demo Narrative (Three Acts + Interactive)

### Act 1: "The Fragmented Lake" (~3 minutes)

**Goal:** Establish the problem — data exists but is unusable without the catalog.

```
NARRATOR: "Imagine you're an analyst at AcmeCorp. Your company has been
operating for years, accumulating data across dozens of systems. Let's
look at what's in your data lake today."

[Display directory tree of data/ folder with file sizes and formats]

NARRATOR: "Eight data sources. Three different formats. Four different
business domains. Some of these sources overlap in time, others succeeded
each other when the company switched platforms."

[Display timeline visualization showing all 8 sources with their date ranges]

NARRATOR: "Now imagine your CEO asks: 'How has the number of video calls
changed since the Pandemic?' You know the data is in here somewhere. But
which files? What format? What are the column names? Do you grep through
every file hoping to find something about video calls?"

[Show the challenge: manually searching through 8 files with different schemas]

NARRATOR: "This is where AstraeaDB changes everything. Let's load an
intelligent metadata catalog."

[Load metadata into AstraeaDB — show graph statistics]
[Optional: show AstraeaDB UI with the metadata graph]
```

### Act 2: "The Intelligent Catalog" (~5 minutes)

**Goal:** Demonstrate temporal succession and multi-perspective discovery.

**Question 1 — Temporal Succession:**
*"How has the number of video calls changed since the Pandemic?"*

```
NARRATOR: "Let's ask the question that stumped us before."

[Orchestrator sends question to LLM]
[Show LLM's tool calls in real time:]
  1. vector_search("video calls pandemic") → finds Teams and Zoom sources
  2. get_node(teams_id) → learns it's CSV, 2018-2021, has duration_minutes
  3. get_node(zoom_id) → learns it's JSON, 2020-2024, has length_minutes
  4. neighbors(teams_id) → discovers SUCCEEDED_BY → Zoom
  5. query_data_source("MS Teams Call Logs", "SELECT ... GROUP BY month")
  6. query_data_source("Zoom Meeting Logs", "SELECT ... GROUP BY month")

[LLM synthesizes answer: call volume by month across both platforms,
 noting the transition period, the pandemic spike, etc.]

NARRATOR: "The catalog didn't just find the data — it understood that
Teams and Zoom are successive sources for the same type of activity,
with an overlap period during the migration."
```

**Question 2 — Multi-Perspective Correlation:**
*"Show me all activity from user U1234 between day 100 and day 110"*

```
NARRATOR: "Now let's look at the same event from multiple perspectives."

[LLM searches catalog → finds logon, HTTP, and email sources all contain user_id]
[LLM queries all three sources for U1234 in the date range]
[LLM correlates: "On day 103, U1234 logged into workstation C1547 at 08:15,
 browsed job posting sites via HTTP from 09:00-11:30, and sent 4 emails with
 attachments to external addresses between 12:00-13:00."]

NARRATOR: "Three different systems. Three different formats. One unified
picture of what this user was doing — all discovered automatically through
the metadata catalog."
```

### Act 3: "Cross-Domain Intelligence" (~4 minutes)

**Goal:** Show the full power — questions that span all four domains.

**Question 3 — Cross-Domain:**
*"What can you tell me about user U1234 across all of our systems?"*

```
[LLM discovers: U1234 exists in security logs (direct match),
 U1234@acmecorp.com in comms and PM data (pattern match),
 and uses the SAME_ENTITY_AS edges to find EMP-1234 in legacy HR
 and WKR-1234 in modern HR]

[LLM queries all 8 sources, synthesizes a complete profile:]
- HR: Hired 2017, Engineering dept, performance trending down in 2023
- Security: Normal logon patterns, but unusual HTTP activity on specific days
- Communications: Meeting frequency dropped 40% in Q3 2024
- PM: Ticket completion rate declined, has open tickets past SLA

NARRATOR: "The catalog connected five different identifier formats across
eight data sources to build a complete picture of one person — something
that would take a human analyst hours of manual investigation."
```

### Recap (~1 minute)

```
NARRATOR: "Let's review what just happened."

[Display statistics table:]
- Questions answered: 3
- Data sources discovered: 8
- Formats handled: CSV, JSONL, JSON, Parquet
- Catalog queries made: ~15
- Data queries made: ~12
- Cross-source correlations: 6
- Identifier mappings resolved: 4

NARRATOR: "Without the intelligent catalog, these questions are
effectively unanswerable — not because the data doesn't exist, but
because no one knows it's there. AstraeaDB turns dead storage into
living intelligence."
```

### Interactive Mode

After the narrated portion, open the floor:

```
--- Interactive Mode ---
Ask any question about the data lake. Type /quit to exit.

Suggested questions:
  - "Which data sources contain information about the Engineering department?"
  - "What happened on the day with the most security events?"
  - "Compare employee meeting frequency before and after the pandemic"
  - "Find all users who appear in both security and HR data"

>
```

---

## 9. Astraea UI Integration (Optional)

Since AstraeaDB runs in server mode (port 7687), the Astraea UI at `/Users/jimharris/Documents/astraea-UI` can connect to visualize the metadata graph.

**Integration points:**
- **Act 1:** After loading the catalog, optionally show the graph in the UI — DataSource nodes connected to Field nodes connected to Concept nodes, color-coded by domain
- **Act 2-3:** As the LLM discovers data sources, the presenter can highlight the relevant subgraph in the UI, showing the path the LLM traversed
- **Interactive:** Leave the UI open alongside the chat for real-time graph exploration

**Implementation:** No code changes needed in the demo — the UI connects to the same AstraeaDB server independently. We just document the optional step:
```bash
# Optional: start Astraea UI for graph visualization
cd /Users/jimharris/Documents/astraea-UI
cargo leptos serve  # or however the UI starts
# Open http://localhost:3000
```

---

## 10. Test Suite

### `test_demo.py` — Four-Layer Test Pyramid

**Layer 1: Data Integrity (6 tests)**
- All 8 data files exist and are readable
- Row counts are within expected ranges
- Column names match metadata definitions
- CSV files parse without errors
- JSON files are valid JSON/JSONL
- Parquet files have correct schema

**Layer 2: AstraeaDB & Metadata (8 tests)**
- AstraeaDB server is reachable (ping)
- Graph has expected node counts (8 DataSource, ~70 Field, ~20 Concept, 4 Domain)
- Graph has expected edge counts
- All DataSource nodes have embeddings
- `find_by_label("DataSource")` returns 8 results
- `vector_search` for "video calls" returns communications sources
- `neighbors` of a DataSource returns its Fields
- Temporal edges exist between successive sources

**Layer 3: DuckDB Tools (6 tests)**
- All 8 sources are queryable via DuckDB
- CSV sources return correct columns
- JSON/JSONL sources parse correctly
- Parquet sources return correct schema
- SQL aggregation queries work (COUNT, GROUP BY)
- Cross-format join is possible (if needed)

**Layer 4: End-to-End Orchestrator (4 tests)**
- Embedding generation works (returns 128-dim normalized vector)
- Temporal succession question finds both Teams and Zoom sources
- Multi-perspective question finds all 3 security sources
- Cross-domain question resolves identifier mappings

---

## 11. Dependencies

### `requirements.txt`

```
# LLM
anthropic>=0.40.0          # Claude API client
httpx>=0.27.0              # HTTP client for Ollama

# Data
duckdb>=1.1.0              # SQL query engine for CSV/JSON/Parquet
faker>=30.0.0              # Synthetic data generation
pyarrow>=17.0.0            # Parquet support (used by DuckDB)
pandas>=2.2.0              # Data manipulation during generation

# AstraeaDB
# Uses astraeadb Python client (from /Users/jimharris/Documents/astraeadb/clients/python)

# Embeddings
# Uses Ollama HTTP API directly (no Python package needed)

# Testing
pytest>=8.0.0
```

---

## 12. Makefile

```makefile
.PHONY: help setup generate-data embeddings ingest validate demo interactive clean

PYTHON := python3
ASTRAEA_BIN := /path/to/astraeadb  # Update to actual path
ASTRAEA_PORT := 7687
DATA_DIR := data

help:  ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# --- Setup Pipeline ---

download-cert:  ## Download CERT Insider Threat dataset
	$(PYTHON) scripts/download_cert.py

generate-data: download-cert  ## Generate all data lake files (CERT subset + synthetic)
	$(PYTHON) scripts/generate_data.py

start-astraea:  ## Start AstraeaDB server
	$(ASTRAEA_BIN) serve --port $(ASTRAEA_PORT) &
	sleep 2
	@echo "AstraeaDB running on port $(ASTRAEA_PORT)"

embeddings:  ## Generate embeddings for all metadata descriptions
	$(PYTHON) scripts/generate_embeddings.py

ingest: start-astraea embeddings  ## Load metadata graph into AstraeaDB
	$(PYTHON) scripts/ingest_metadata.py

validate: ingest  ## Validate data files and metadata consistency
	$(PYTHON) scripts/validate.py

setup: generate-data validate  ## Full setup pipeline (download → generate → embed → ingest → validate)
	@echo "Setup complete. Run 'make demo' to start the presentation."

# --- Demo ---

demo: validate  ## Run the full narrated demo + interactive chat
	$(PYTHON) -m src.orchestrator --mode full

narrated:  ## Run only the narrated walkthrough (no interactive)
	$(PYTHON) -m src.orchestrator --mode narrated

interactive:  ## Run only the interactive chat (skip narration)
	$(PYTHON) -m src.orchestrator --mode interactive

# --- Development ---

test:  ## Run test suite
	$(PYTHON) -m pytest test_demo.py -v

clean:  ## Remove generated data and AstraeaDB state
	rm -rf $(DATA_DIR)/cert_raw/
	rm -rf $(DATA_DIR)/security/ $(DATA_DIR)/communications/ $(DATA_DIR)/hr/ $(DATA_DIR)/projects/
	rm -rf metadata/embeddings.json
	@echo "Cleaned generated data. Re-run 'make setup' to regenerate."
```

---

## 13. Configuration

### `config.py`

```python
import os

# --- AstraeaDB ---
ASTRAEA_HOST = os.getenv("ASTRAEA_HOST", "127.0.0.1")
ASTRAEA_PORT = int(os.getenv("ASTRAEA_PORT", "7687"))
ASTRAEA_BIN = os.getenv("ASTRAEA_BIN", "astraeadb")

# --- LLM ---
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")  # "anthropic" or "ollama"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "gemma3:12b")

# --- Embeddings ---
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "embeddinggemma")
EMBEDDING_DIM_RAW = 768
EMBEDDING_DIM = 128  # Matryoshka truncation

# --- Data Generation ---
USER_COUNT = 200                # Number of synthetic users
CERT_SUBSET_USERS = 200         # Users to extract from CERT
SEED = 42                       # Reproducibility

# --- Paths ---
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
METADATA_DIR = os.path.join(os.path.dirname(__file__), "metadata")
CERT_RAW_DIR = os.path.join(DATA_DIR, "cert_raw")

# --- Demo ---
MAX_TOOL_ROUNDS = 8
INTERACTIVE_MODE = os.getenv("INTERACTIVE", "false").lower() == "true"
```

---

## 14. Implementation Phases

### Phase 1: Foundation (Est. effort: Medium)
1. Set up project structure and `config.py`
2. Write `scripts/download_cert.py` — download and validate CERT dataset
3. Write `scripts/generate_data.py` — create all 8 data sources
4. Verify all files are readable with DuckDB
5. Write basic `test_demo.py` Layer 1 tests (data integrity)

**Deliverable:** 8 data files in `data/`, all queryable with DuckDB.

### Phase 2: Metadata Graph (Est. effort: Medium)
1. Define all metadata in `metadata/*.json` files
2. Write `scripts/generate_embeddings.py`
3. Write `scripts/ingest_metadata.py`
4. Write `test_demo.py` Layer 2 tests (AstraeaDB)
5. Document graph schema in `schema.md`

**Deliverable:** Metadata graph loaded in AstraeaDB, searchable via MCP.

### Phase 3: Query Tools (Est. effort: Low-Medium)
1. Implement `src/duckdb_tools.py`
2. Implement `src/mcp_bridge.py` (adapt from GraphRAG demo)
3. Implement `src/embeddings.py` (adapt from GraphRAG demo)
4. Write `test_demo.py` Layer 3 tests (DuckDB tools)

**Deliverable:** Both metadata discovery and data querying work end-to-end.

### Phase 4: Orchestrator & Demo (Est. effort: Medium-High)
1. Implement `src/orchestrator.py` with tool-calling loop
2. Implement `src/narrator.py` with scripted content
3. Implement `src/display.py` for formatted output
4. Write system prompt and tune LLM behavior
5. Write `test_demo.py` Layer 4 tests (end-to-end)
6. Create `voiceover.md` presentation script

**Deliverable:** Full working demo — narrated walkthrough + interactive chat.

### Phase 5: Polish (Est. effort: Low)
1. Write `README.md` with setup instructions
2. Finalize `Makefile`
3. Test full pipeline from clean state (`make clean && make setup && make demo`)
4. Document Astraea UI integration (optional)
5. Tune demo questions and narration for presentation impact

**Deliverable:** Presentation-ready demo.

---

## 15. Risk & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| CERT dataset download fails or changes | Blocks data generation | Cache downloaded files; include fallback to fully-synthetic security data |
| Ollama embedding model not available | Blocks metadata ingestion | Support pre-computed embeddings fallback; document Ollama setup in README |
| LLM struggles with multi-step discovery | Demo looks bad | Tune system prompt; add few-shot examples; use Claude (stronger reasoning) as default |
| DuckDB can't parse a generated file | Data query fails | Validate all files with DuckDB in generation step; fix format issues early |
| AstraeaDB server not running during demo | Everything fails | Add health check to demo startup; clear error message with fix instructions |
| Demo takes too long per question | Presentation drags | Set timeouts; pre-warm LLM context; optimize DuckDB queries |
