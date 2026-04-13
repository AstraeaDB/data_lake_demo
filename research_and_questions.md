# Data Lake Demo: Research, Ideas & Development Questions

## 1. Concept Overview

### What This Demo Is

This demo shows how **AstraeaDB** can serve as an intelligent metadata catalog for a fragmented enterprise data lake. Unlike the GraphRAG demo (which stored literary content in the graph) or the cyber graph demo (which stored security telemetry in the graph), this demo uses AstraeaDB to store **metadata about data sources** — not the data itself.

The graph contains:
- **Data source nodes** — semantic descriptions, format info, time coverage, origin system
- **Schema/field nodes** — column names, data types, semantic descriptions of what each field represents
- **Concept nodes** — abstract business concepts ("video conferencing," "employee onboarding," "authentication event") that link semantically related fields across disparate sources
- **Temporal edges** — when each source was active, when systems were migrated
- **Semantic embeddings** — on every node, enabling the LLM to find relevant sources via natural language

The actual data lives in files (CSV, JSON, Parquet, etc.) simulating a data lake. When a user asks a question like *"How has the number of video calls changed since the Pandemic?"*, the flow is:

1. LLM queries AstraeaDB (via MCP tools) to find relevant data sources
2. AstraeaDB returns: "Teams call logs (2018–2020, CSV format, columns: date, duration, participants...) and Zoom call logs (2020–2024, JSON format, fields: meeting_start, length_minutes, attendees...)"
3. LLM uses file-reading tools to query the actual data files
4. LLM synthesizes the answer across both sources, understanding the field mappings

### What Makes This Different From Existing Data Catalogs

Existing tools like DataHub, OpenMetadata, and Amundsen use keyword search and manual tagging. This demo shows:
- **Semantic discovery** — find sources by meaning, not just column names (e.g., "employee departure" finds both `attrition_flag` in HR data and `termination_date` in payroll data)
- **Cross-source linking** — the graph explicitly connects fields across sources that describe the same concept
- **Temporal awareness** — the catalog knows which sources cover which time periods, enabling questions that span system migrations
- **LLM-native interface** — instead of a search UI, the catalog exposes MCP tools that let an LLM reason about data discovery as part of answering a question

---

## 2. Data Strategy: Synthetic vs. Open Source

### Option A: Fully Synthetic Data

**Pros:**
- Complete control over narrative — can design exact scenarios we want to demonstrate
- No licensing concerns
- Can ensure cross-source consistency (same employee IDs across HR, IT, communications)
- Can control data volume precisely
- Can design "interesting" patterns that demonstrate the tool well

**Cons:**
- Time-consuming to make realistic
- May feel contrived or toy-like
- No real-world messiness to demonstrate robustness
- Harder to justify claims about enterprise applicability

### Option B: Open Source Datasets

**Pros:**
- Real-world messiness adds credibility
- Many high-quality options available (see Section 3)
- Faster to get started — data already exists
- Can demonstrate handling real format variation

**Cons:**
- Datasets won't naturally reference each other (no shared employee IDs across Kaggle datasets)
- May need significant preprocessing to fit the narrative
- Licensing considerations
- May contain more data than needed, requiring careful subsetting

### Option C: Hybrid Approach (Recommended)

Use **open source datasets as templates** with **synthetic bridging data** to connect them:
- Take real dataset schemas and formats, but generate synthetic content that shares entity IDs across sources
- Preserves realistic column names, data types, and format variation
- Enables the cross-source correlation narrative
- Can use Python's Faker or SDV (Synthetic Data Vault) to generate connected data

> **QUESTION FOR JIM:** Which approach do you prefer?
> - [ ] A) Fully synthetic — maximum narrative control
> - [ ] B) Open source only — maximum realism
> - [X] C) Hybrid — open source schemas with synthetic connected content
> - [ ] D) Other (describe):
>
> **Follow-up:** How important is it that the demo data feel "messy" and realistic vs. clean and clearly demonstrative?
ANSWER: It should feel as realistic as possible
---

## 3. Available Open Source Datasets by Domain

Based on research, here are the strongest candidates organized by enterprise domain:

### HR / People Operations
| Dataset | Records | Format | Key Fields | Notes |
|---------|---------|--------|------------|-------|
| IBM HR Analytics (Kaggle) | 1,470 | CSV | department, role, income, attrition, satisfaction | Fictional, IBM-created, very popular |
| Employee Dataset All-in-One (Kaggle) | Multi-table | CSV/ZIP | employee data + training + recruitment as separate tables | CC0 license, 3 related tables |
| Employee Absenteeism (Kaggle) | — | CSV | attendance/absence tracking | Different system perspective on same employees |

### IT Operations / Helpdesk
| Dataset | Records | Format | Key Fields | Notes |
|---------|---------|--------|------------|-------|
| IT Helpdesk Dataset (Kaggle) | — | CSV | Internal IT support tickets | "Old system" candidate |
| IT Service Ticket Classification (Kaggle) | — | CSV | Classified IT tickets | "New system" candidate |
| Support Ticket Priority (Kaggle) | 50K | CSV | Priority-classified tickets | Alternative "new system" |
| Helpdesk Event Log (Mendeley) | — | Process-mining format | Italian software company ticketing | Very different format — good for diversity |

### Security / Authentication (Multi-Perspective)
| Dataset | Records | Format | Key Fields | Notes |
|---------|---------|--------|------------|-------|
| CERT Insider Threat (CMU/DARPA) | Multi-file | CSV | Logon, USB, HTTP, file access, email — all for same users | **Best multi-perspective dataset available** |
| Login Data for Risk-Based Auth (Kaggle) | — | CSV | Auth events with timestamps, IPs, user agents | Pairs with firewall data |
| Internet Firewall Data (Kaggle) | — | CSV | Firewall allow/deny/drop decisions | Pairs with auth data |
| SecRepo.com samples | Various | Multiple formats | Proxy logs, auth.log, Bro/Zeek logs | Real format diversity |

### Financial / Transactions
| Dataset | Records | Format | Key Fields | Notes |
|---------|---------|--------|------------|-------|
| CFPB Consumer Complaints | 7.8M+ | CSV, JSON | Complaints from 2011–present | Real government data |
| Financial Transactions (Kaggle) | — | CSV | Transactions with fraud labels | Pairs with complaints |
| Invoices Dataset (Kaggle) | — | CSV | Billing perspective | Third perspective on same events |

### Communications
| Dataset | Records | Format | Key Fields | Notes |
|---------|---------|--------|------------|-------|
| Enron Email Dataset | 600K+ | Raw text/CSV | Real corporate emails, 158 employees | Canonical corporate email dataset |
| Slack Queries Dataset (Kaggle) | — | CSV | Slack message data | "New platform" to Enron's "old platform" |
| Meeting Conversation Dataset (Kaggle) | — | CSV | Meeting transcripts | Could represent video conferencing logs |

### Project Management
| Dataset | Records | Format | Key Fields | Notes |
|---------|---------|--------|------------|-------|
| Apache Jira Issues (Zenodo) | — | Various | Real Jira data from Apache Foundation | Authentic project tracking |
| Project Management Dataset (Kaggle) | — | CSV | Generic PM data | Simpler alternative |

> **QUESTION FOR JIM:** Which enterprise domains are most important to include? Pick your top 3-4:
> - [X] HR / People Operations
> - [ ] IT Operations / Helpdesk
> - [X] Security / Authentication
> - [ ] Financial / Transactions
> - [X] Communications (email/messaging/video calls)
> - [X] Project Management
> - [ ] Sales / CRM
> - [ ] Other:
>
> **QUESTION FOR JIM:** The CERT Insider Threat dataset from CMU stands out as uniquely well-suited — it has 5 different log types (logon, USB, HTTP, file access, email) for the same 1,000 users over 500 days. Should we use it as a centerpiece, or does the security focus overlap too much with the cyber graph demo?

ANSWER: Please use that dataset
---

## 4. Data Segregation & Fragmentation Strategy

The demo needs to simulate a fragmented enterprise data lake without being overwhelming. Here are the design options:

### Dimension 1: How Many Data Sources?

| Option | Sources | Complexity | Demo Time |
|--------|---------|------------|-----------|
| Minimal | 4–5 | Easy to explain, clear narrative | Short |
| Moderate | 8–10 | Richer cross-connections, more realistic | Medium |
| Full | 12–15 | Very realistic, but harder to keep coherent | Long |

> **QUESTION FOR JIM:** How many distinct data sources feel right? The cyber graph demo used 5 (auth, process, flows, DNS, redteam). The sweet spot for a demo that's both impressive and followable is probably 6–8.

ANSWER: Use 6-8, as needed

### Dimension 2: Format Distribution

For maximum impact, the data sources should use varied formats:

| Format | Count | Rationale |
|--------|-------|-----------|
| CSV | 2–3 | The "legacy" default — older systems export CSV |
| JSON / JSONL | 2–3 | Modern APIs and log systems often use JSON |
| Parquet | 1–2 | Analytics-focused data, columnar storage |
| Delta (optional) | 1 | Shows modern lakehouse format support |

> **QUESTION FOR JIM:** Should we include Delta format? It adds realism but also adds a dependency (delta-rs library). Parquet alone demonstrates columnar formats. Is the added complexity worth it?

ANSWER: No, keep it simple

### Dimension 3: Time Periods

To show temporal succession, we need data sources that:
- **Overlap** — two systems active during the same period (multi-perspective)
- **Succeed** — one system replaced another (temporal succession)
- **Gap** — brief period where neither old nor new system was fully active (realistic)

Example timeline:
```
2017    2018    2019    2020    2021    2022    2023    2024
|-------|-------|-------|-------|-------|-------|-------|
                                                        
HR System (Legacy CSV)  ████████████████████░░░░░░░░░░░  (2017–2021)
HR System (Modern JSON) ░░░░░░░░░░░░░░░░░░████████████  (2021–2024)
                                                        
Teams Call Logs (CSV)   ░░░░████████████████░░░░░░░░░░░  (2018–2021)
Zoom Call Logs (JSON)   ░░░░░░░░░░░░░░░░░░████████████  (2020–2024)
                        ^--- overlap period ---^          
                                                        
Old Ticketing (CSV)     ████████████████░░░░░░░░░░░░░░░  (2017–2020)
New Ticketing (Parquet) ░░░░░░░░░░░░░░░░████████████████  (2020–2024)
                                                        
Auth Logs (JSONL)       ██████████████████████████████████ (2017–2024, continuous)
Firewall Logs (CSV)     ██████████████████████████████████ (2017–2024, continuous)
WAF Logs (JSON)         ░░░░░░░░░░████████████████████████ (2019–2024, added later)
```

> **QUESTION FOR JIM:** Does a timeline like this feel right? Any specific systems or scenarios you want to see represented?

ANSWER: This seems good to me

### Dimension 4: Data Volume

For a demo, we need enough data to be credible but not so much that it's slow or expensive:

| Source | Rows | Size | Rationale |
|--------|------|------|-----------|
| Per source | 500–5,000 | 50KB–2MB | Small enough to bundle in git, large enough to demonstrate real queries |
| Total lake | 5,000–20,000 | 500KB–10MB | Manageable but non-trivial |

> **QUESTION FOR JIM:** Is this the right scale, or should we go bigger (e.g., 100K+ rows per source) to be more impressive? Larger data would require the demo machine to have more resources, but would be more credible as "enterprise-scale."

ANSWER: The demo machine will likely be this Mac with the M5Max and 128GB of RAM, so go a little on the larger side

---

## 5. Demonstrating Temporal Connections (Same Data Type, Different Periods)

### Scenario A: Video Conferencing Platform Migration
- **Source 1:** "Microsoft Teams" call logs (CSV), 2018–2021
  - Columns: `call_date`, `organizer_email`, `duration_minutes`, `participant_count`, `call_type` (audio/video/screenshare)
- **Source 2:** "Zoom" meeting logs (JSON), 2020–2024
  - Fields: `meeting_start`, `host`, `length_minutes`, `attendees[]`, `meeting_type`, `recording_available`

**Demo question:** *"How has the number of video calls changed since the Pandemic?"*
- LLM must find both sources via AstraeaDB
- Understand that `duration_minutes` ≈ `length_minutes` and `participant_count` relates to `attendees[].length`
- Combine data across the overlap period (2020–2021) and succession period (2021+)
- Account for the schema differences in its answer

### Scenario B: IT Ticketing System Migration
- **Source 1:** Old helpdesk system (CSV), 2017–2020
  - Columns: `ticket_id`, `opened`, `closed`, `category`, `priority`, `assignee`, `resolution`
- **Source 2:** New ITSM platform (Parquet), 2020–2024
  - Columns: `incident_number`, `created_at`, `resolved_at`, `service_category`, `urgency`, `assigned_group`, `resolution_code`, `sla_met`

**Demo question:** *"What's the trend in IT ticket resolution times over the past 7 years?"*
- Different column names for the same concepts
- Different date formats
- New system has fields (SLA tracking) that old system didn't

### Scenario C: HR System Migration
- **Source 1:** Legacy HRIS (CSV), 2017–2021
  - Employee demographics, performance ratings, basic compensation
- **Source 2:** Modern HCM platform (JSON), 2021–2024
  - Richer schema: skills, learning paths, engagement scores, goals, OKRs

**Demo question:** *"How has employee attrition in the engineering department changed?"*

> **QUESTION FOR JIM:** Which temporal succession scenarios are most compelling? Rank them or suggest alternatives:
> 1. Video conferencing migration (Teams → Zoom)
> 2. IT ticketing migration (legacy → modern ITSM)
> 3. HR system migration (basic → modern HCM)
> 4. Email migration (on-prem Exchange → cloud M365 / or email → Slack)
> 5. Other:


ANSWER: Pick three demo questions based on the sources selected in the answers above
---

## 6. Demonstrating Multi-Perspective Data (Same Event, Different Sources)

### Scenario A: Security Event Correlation
- **Firewall logs** show: connection from IP X to server Y on port 443 at time T
- **WAF logs** show: HTTP request from IP X to application Z with specific URI at time T+1s
- **Auth logs** show: user login from IP X to application Z at time T+2s

**Demo question:** *"Show me all activity from IP address 10.0.1.47 last Tuesday"*
- LLM finds all three sources that contain IP address data
- Correlates entries by timestamp and IP
- Presents a unified timeline

### Scenario B: Employee Event Correlation
- **HR system** shows: employee Jane Smith started on 2023-03-15
- **IT ticketing** shows: ticket "New laptop setup for jsmith@company.com" created 2023-03-14
- **Auth logs** show: first login for jsmith@company.com on 2023-03-15 at 9:07 AM
- **Training system** shows: "New Employee Orientation" completion for employee #4872 on 2023-03-15

**Demo question:** *"Walk me through what happens when a new employee starts"*
- LLM must discover that all four sources contain onboarding-related data
- Correlate across different identifier formats (name vs email vs employee number)
- Present the full picture

### Scenario C: Financial Event Correlation
- **Transaction system** shows: charge of $247.50 to vendor "Acme Corp" on PO #12345
- **Invoice system** shows: invoice from Acme Corp for $247.50 referencing PO #12345
- **Expense system** shows: reimbursement request for $247.50 by employee Bob, category "Office Supplies"
- **Budget system** shows: $247.50 charged against Q3 office supplies budget for department Engineering

**Demo question:** *"How much did the Engineering department spend on office supplies in Q3?"*

> **QUESTION FOR JIM:** Which multi-perspective scenarios are most compelling? Rank them or suggest alternatives:
> 1. Security event correlation (firewall + WAF + auth logs)
> 2. Employee lifecycle (HR + IT + auth + training)
> 3. Financial event trail (transactions + invoices + expenses + budget)
> 4. Other:

ANSWER: the Security event correlation is the most compelling
>
> **QUESTION FOR JIM:** For multi-perspective correlation, should the demo show the LLM correlating by:
> - [ ] Shared identifiers (same employee ID across systems) — easier, but less impressive
> - [ ] Semantic understanding (realizing that "jsmith@company.com" and employee #4872 are the same person via context) — harder, more impressive
> - [X] Both — some sources share IDs, others require semantic bridging

---

## 7. Architecture & User Interface

### How Should the User Interact With the Demo?

**Option A: CLI Chat (like GraphRAG demo)**
- Interactive REPL where user types questions
- Model calls MCP tools against AstraeaDB to find data sources
- Model then reads data files and synthesizes answers
- Pros: Fastest to build, proven pattern
- Cons: Less visually impressive

**Option B: Web UI Chat**
- Browser-based chatbot interface (e.g., Streamlit, Gradio, or custom)
- Same underlying flow but with a visual interface
- Could show the "search path" — which data sources the LLM considered and selected
- Pros: More polished, can visualize the discovery process
- Cons: More work to build

**Option C: Narrated Demo (like cyber graph demo)**
- Scripted three-act demonstration
- Walkthrough of specific questions with pre-planned narrative
- Pros: Most controlled, best for presentations
- Cons: Not interactive

**Option D: Hybrid — Narrated demo with live chat**
- Scripted walkthrough that establishes the scenario
- Then opens an interactive chat for audience questions
- Pros: Best of both worlds
- Cons: Most complex

> **QUESTION FOR JIM:** What's the primary context for this demo?
> - [X] A) Live presentation / conference talk
> - [ ] B) Recorded video demo
> - [ ] C) Self-service exploration (someone runs it themselves)
> - [ ] D) Sales/partner meeting
> - [ ] E) Multiple of the above (which is primary?):
>
> **QUESTION FOR JIM:** Which interface approach?
> - [ ] A) CLI chat (fastest to build)
> - [ ] B) Web UI (more polished)
> - [ ] C) Narrated script (most controlled)
> - [X] D) Hybrid narrated + interactive

---

## 8. LLM & Embedding Strategy

### Which LLM for the Chatbot?

The GraphRAG demo deliberately used a tiny 4B model (gemma3:4b via Ollama) to prove that graph structure compensates for model size. The cyber graph demo used Claude (Anthropic API) or Ollama.

**Options:**
| Model | Pros | Cons |
|-------|------|------|
| Claude (Anthropic API) | Best reasoning, native tool use, handles complex multi-step discovery well | Requires API key, cost |
| gemma3:4b (Ollama) | Free, local, demonstrates the "small model + smart catalog" story | May struggle with complex multi-source reasoning |
| Llama 3 8B (Ollama) | Free, local, better reasoning than 4B | Still may struggle with complex queries |
| Claude via MCP | Uses Claude Code as the interface directly | Blurs demo vs. tooling boundary |

> **QUESTION FOR JIM:** Which LLM approach?
> - [ ] A) Claude API — best results, shows enterprise-grade capability
> - [ ] B) Small local model (Ollama) — shows that even small models work with good metadata
> - [X] C) Configurable — support both, default to Claude
> - [ ] D) Other preference:

### Embedding Model

Following the GraphRAG demo pattern, we'd use Ollama's `embeddinggemma` with Matryoshka truncation to 128 dimensions. This keeps everything local and free.

> **QUESTION FOR JIM:** Is local embeddings (Ollama) the right choice, or should we use OpenAI/Anthropic embeddings for higher quality? The metadata descriptions are relatively simple text, so local embeddings should be sufficient.

ANSWER: Local embeddings

---

## 9. Graph Schema Design

### Proposed Node Types

```
DataSource          — represents a file/table in the data lake
  properties: name, description, format (csv/json/parquet/delta),
              file_path, origin_system, active_from, active_to,
              row_count, last_updated
  embedding: semantic description of the data source

Field               — represents a column/field within a data source
  properties: name, data_type, description, nullable, sample_values
  embedding: semantic description of what this field represents

Concept             — abstract business concept that links related fields
  properties: name, description, domain (HR/IT/Security/Finance/etc.)
  embedding: semantic description of the concept

Domain              — broad category of business data
  properties: name, description
  embedding: semantic description of the domain
```

### Proposed Edge Types

```
HAS_FIELD           DataSource → Field       (a source contains this field)
MAPS_TO_CONCEPT     Field → Concept          (this field represents this concept)
SUCCEEDED_BY        DataSource → DataSource   (temporal succession)
OVERLAPS_WITH       DataSource → DataSource   (covers same time period)
PERSPECTIVE_OF      DataSource → Concept      (provides a viewpoint on this concept)
BELONGS_TO_DOMAIN   DataSource → Domain       (categorization)
RELATES_TO          Concept → Concept         (semantic relationship between concepts)
SAME_ENTITY_AS      Field → Field             (different names for same thing across sources)
```

### Example Subgraph

```
[Domain: Communications]
    ↑ BELONGS_TO_DOMAIN
[DataSource: "Teams Call Logs" (CSV, 2018-2021)]
    ├─ HAS_FIELD → [Field: "duration_minutes" (int)]
    │                 └─ MAPS_TO_CONCEPT → [Concept: "Call Duration"]
    │                                          ↑ MAPS_TO_CONCEPT
    ├─ HAS_FIELD → [Field: "participant_count"]    │
    │                 └─ MAPS_TO_CONCEPT → [Concept: "Meeting Size"]
    │                                          ↑ MAPS_TO_CONCEPT
    └─ SUCCEEDED_BY → [DataSource: "Zoom Meeting Logs" (JSON, 2020-2024)]
                          ├─ HAS_FIELD → [Field: "length_minutes" (int)]
                          │                 └─ MAPS_TO_CONCEPT → [Concept: "Call Duration"]
                          └─ HAS_FIELD → [Field: "attendees" (array)]
                                            └─ MAPS_TO_CONCEPT → [Concept: "Meeting Size"]
```

> **QUESTION FOR JIM:** Does this graph schema feel right? Anything to add or simplify? Key considerations:
> - Should we include a `System` node type (e.g., "Microsoft Teams", "Zoom") separate from `DataSource`?
> - Should `Field` nodes include sample values to help the LLM understand what the data looks like?
> - Should we add `User`/`Entity` nodes that represent the actual entities in the data (employees, IPs, etc.) or keep the graph purely about metadata?

ANSWERS: This seems right. The data source name should be descriptive enough not to need a separate system property. Field should include type information and whether or not it is nullable, such as Avro schema, and maybe a small sample. Keep the graph about metadata
---

## 10. MCP Tool Design

The LLM would have access to these tools via AstraeaDB's MCP server plus custom tools for reading the data lake:

### AstraeaDB MCP Tools (metadata discovery)
- `find_by_label` — find all DataSources, Fields, Concepts
- `get_node` — get full details of a source/field/concept
- `neighbors` — explore connections (what fields does this source have? what concept does this field map to?)
- `vector_search` — "find data sources about video conferencing"
- `hybrid_search` — find sources that are both semantically relevant and structurally connected
- `query` (GQL) — structured queries like "find all sources active between 2020-2022 in the Communications domain"

### Data Lake Reading Tools (custom, separate from AstraeaDB)
- `read_csv(file_path, query)` — read and optionally filter/aggregate CSV data
- `read_json(file_path, query)` — read and optionally filter/aggregate JSON data
- `read_parquet(file_path, query)` — read and optionally filter/aggregate Parquet data
- `preview_data(file_path, n_rows)` — show first N rows of any supported format

> **QUESTION FOR JIM:** Should the data reading tools be:
> - [ ] A) Simple file readers (LLM loads data into context and reasons over it)
> - [ ] B) Query-capable (LLM can specify filters/aggregations, tool returns results) — more scalable but more complex
> - [X] C) DuckDB-backed (use DuckDB to query any format with SQL) — most powerful, single tool for all formats
>
> **QUESTION FOR JIM:** Should we also include an AstraeaDB UI visualization component (like the cyber graph demo optionally used)?

ANSWER: Make it optional to use the UI at /Users/jimharris/Documents/astraea-UI
---

## 11. Demo Flow & Narrative

### Proposed Three-Act Structure (following cyber graph demo pattern)

**Act 1: "The Fragmented Lake"**
- Show the data lake: 6–8 files in different formats, different schemas
- Demonstrate the problem: try to answer a question manually — which files do you even look at?
- Load the metadata catalog into AstraeaDB
- Show the graph: data sources connected to fields connected to concepts

**Act 2: "The Intelligent Catalog"**
- User asks: *"How has the number of video calls changed since the Pandemic?"*
- LLM searches AstraeaDB → finds Teams logs (2018–2021) and Zoom logs (2020–2024)
- LLM reads both files, maps `duration_minutes` to `length_minutes`, etc.
- LLM produces answer with data from both sources, noting the platform transition

- User asks: *"Show me all activity related to the security incident on March 15th"*
- LLM searches AstraeaDB → finds firewall, WAF, and auth logs all contain relevant data
- LLM queries each source for March 15th events, correlates by IP/timestamp
- LLM produces unified timeline

**Act 3: "Cross-Domain Intelligence"**
- User asks a question that spans multiple domains
- E.g., *"Our engineering team's productivity seems down this quarter — what can we find?"*
- LLM discovers HR data (headcount, attrition), project management data (tickets closed), IT data (system outages that affected engineering), communications data (meeting frequency)
- LLM synthesizes insights across all sources

**Recap:**
- Show statistics: how many sources searched, how many fields mapped, how the graph enabled discovery
- Compare with/without the catalog (raw LLM can't find the data)

> **QUESTION FOR JIM:** Does this three-act structure work? Would you restructure it?
>

ANSWER: yes

> **QUESTION FOR JIM:** What's the "killer question" — the single most impressive query that would make an audience say "I need this"? The video conferencing one from the CLAUDE.md is good, but we could workshop something even more compelling.

ANSWER: The initial demo is for a company that produces storage solutions for cloud providers. They want to offer features that can demonstrate more value add. The killer question is: "can a data storage solution be "intelligent" and enable customers to find and use data they didn't even realize they were keeping?"

---

## 12. Technical Implementation Questions

> **QUESTION FOR JIM:** What language should the demo be written in? The existing demos use Python. Should we stick with Python for consistency?

ANSWER: Python is fine

> **QUESTION FOR JIM:** Should the demo run against a live AstraeaDB server (started separately) or use embedded mode? The cyber graph demo used a server; the MCP integration can work either way.

ANSWER: If embedded can still use the UI, use embedded, otherwise use server mode

> **QUESTION FOR JIM:** How should the demo be packaged for others to run?
> - [X] A) Simple Python scripts with a README (like existing demos)
> - [ ] B) Docker Compose (AstraeaDB + demo app)
> - [X] C) Makefile-driven setup (like cyber graph demo)
> - [ ] D) All of the above

> **QUESTION FOR JIM:** Should the data generation/ingestion be a separate step from the demo itself? (i.e., `make setup` to generate data and load metadata, then `make demo` to run the interactive part)

---

## 13. Summary of Key Decisions Needed

| # | Decision | Options | My Recommendation |
|---|----------|---------|-------------------|
| 1 | Data strategy | Synthetic / Open source / Hybrid | Hybrid — real schemas, synthetic connected content |
| 2 | Enterprise domains | HR, IT, Security, Finance, Comms, PM | Pick 3–4 that tell a cohesive story |
| 3 | Number of data sources | 4–5 / 6–8 / 10+ | 6–8 for the sweet spot |
| 4 | Data formats | CSV only / CSV+JSON / CSV+JSON+Parquet+Delta | CSV + JSON + Parquet (skip Delta) |
| 5 | Data volume per source | Hundreds / Thousands / Tens of thousands | 1,000–5,000 rows per source |
| 6 | Temporal scenarios | Video calls / IT tickets / HR / Email | At least 2 temporal succession pairs |
| 7 | Multi-perspective scenarios | Security / Employee lifecycle / Financial | At least 1 multi-perspective cluster |
| 8 | Interface | CLI / Web UI / Narrated / Hybrid | Depends on audience |
| 9 | LLM | Claude API / Local Ollama / Configurable | Configurable, default Claude |
| 10 | Data reading approach | Simple readers / Query-capable / DuckDB | DuckDB for maximum flexibility |
| 11 | Graph schema | As proposed / Simplified / Extended | As proposed, iterate |
| 12 | Implementation language | Python / Other | Python for consistency |

---

## Next Steps

Once these questions are answered, I'll create a detailed implementation plan covering:
1. Data generation scripts
2. AstraeaDB metadata graph schema and ingestion
3. MCP tool configuration
4. Demo orchestrator architecture
5. Test suite design
6. Setup and packaging
