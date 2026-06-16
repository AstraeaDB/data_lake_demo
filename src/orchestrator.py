"""Main demo orchestrator.

Runs the three-act narrated demo followed by interactive chat.
Manages the LLM, AstraeaDB metadata discovery, and DuckDB data queries.
"""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from src import display
from src.duckdb_tools import get_tools, tool_list_data_sources, tool_preview_data_source, tool_query_data_source
from src.embeddings import check_ollama_available, embed_text
from src.eunomia_bridge import EunomiaBridge, MetricsCollector
from src.mcp_bridge import DirectBridge

# LLM client setup
try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


SYSTEM_PROMPT = """\
You are a data analyst assistant with access to an enterprise data lake and \
an intelligent metadata catalog powered by AstraeaDB.

You have two types of tools:

## Metadata Discovery Tools (AstraeaDB)
These help you find what data exists, what format it's in, what fields it \
contains, and how sources relate to each other:
- search_catalog: Find data sources or fields semantically similar to a query
- get_source_details: Get full details and field descriptions for a source
- find_related_sources: Find sources connected by temporal succession or overlap

## Data Query Tools (DuckDB)
These let you query the actual data files:
- list_data_sources: Show all available data sources with row counts
- preview_data_source: See schema and sample rows from a source
- query_data_source: Run SQL queries against a source (reference as 'data')

## How to work efficiently:
1. Use search_catalog or list_data_sources to find relevant sources. If \
search_catalog fails (e.g. embedding service unavailable), fall back to \
list_data_sources and preview_data_source to find what you need.
2. Use PARALLEL tool calls whenever possible. For example, if you need details \
on two sources, call get_source_details for both in the same turn.
3. Similarly, run queries on multiple sources in the same turn when you can.
4. Once you have enough data to answer, STOP using tools and give your answer. \
Do not keep querying if you already have what you need.
5. Always cite which data sources you used and explain any field mappings.

Important: Different sources may use different identifiers for the same person:
- Security logs use "UXXXX" format (e.g., U0042)
- Communications and PM use "UXXXX@acmecorp.com" email format
- Legacy HR uses "EMP-XXXX" format
- Modern HR uses "WKR-XXXX" format
The numeric portion is always the same (0042 in the examples above).
"""

# Tool definitions for Claude API
TOOL_DEFINITIONS = [
    {
        "name": "list_data_sources",
        "description": "List all available data sources in the data lake with their formats and row counts.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "preview_data_source",
        "description": "Preview a data source: see its column schema, data types, and first few rows of actual data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source_name": {
                    "type": "string",
                    "description": "Name of the data source (e.g., 'CERT Logon Events', 'Zoom Meeting Logs')",
                },
                "n_rows": {
                    "type": "integer",
                    "description": "Number of sample rows to show (default 5)",
                    "default": 5,
                },
            },
            "required": ["source_name"],
        },
    },
    {
        "name": "query_data_source",
        "description": "Execute a SQL query against a data source. Reference the source table as 'data' in your SQL. Supports full SQL including WHERE, GROUP BY, ORDER BY, JOIN, aggregations, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source_name": {
                    "type": "string",
                    "description": "Name of the data source to query",
                },
                "sql": {
                    "type": "string",
                    "description": "SQL query to execute. Use 'data' as the table name. Example: SELECT COUNT(*) FROM data WHERE user = 'U0042'",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum rows to return (default 100)",
                    "default": 100,
                },
            },
            "required": ["source_name", "sql"],
        },
    },
    {
        "name": "search_catalog",
        "description": "Search the AstraeaDB metadata catalog using semantic (vector) search. Finds data sources, fields, or concepts that are semantically similar to your natural language query.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language description of what you're looking for (e.g., 'video conferencing data', 'employee performance ratings', 'authentication events')",
                },
                "k": {
                    "type": "integer",
                    "description": "Number of results to return (default 10)",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_source_details",
        "description": "Get full metadata details about a specific data source, including its description, format, time range, and all fields with their descriptions and types.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source_name": {
                    "type": "string",
                    "description": "Name of the data source",
                },
            },
            "required": ["source_name"],
        },
    },
    {
        "name": "find_related_sources",
        "description": "Find data sources related to a given source through the metadata graph. Returns sources connected by SUCCEEDED_BY (temporal succession), OVERLAPS_WITH (same time period), or shared Concepts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source_name": {
                    "type": "string",
                    "description": "Name of the data source to find relations for",
                },
            },
            "required": ["source_name"],
        },
    },
]


class DemoOrchestrator:
    """Main orchestrator for the data lake demo."""

    def __init__(self):
        self.duckdb = get_tools()
        self._source_node_map: dict[str, int] = {}  # source name → node ID

        # Try to connect to AstraeaDB, but don't fail if it's not running
        try:
            self.db = DirectBridge()
            self.db.load_id_map()
            self._build_source_map()
            self._astraea_available = True
        except Exception as e:
            print(f"  Note: AstraeaDB not available ({e}). Using metadata files as fallback.")
            self.db = None
            self._astraea_available = False
            self._load_id_map_from_file()

        # Eunomia working-memory cache in front of the three metadata tools.
        # Disabled (no-op) unless EUNOMIA_URL is set; metrics are collected
        # either way so the disabled run becomes the "before" baseline.
        self.eunomia = EunomiaBridge()
        self.metrics = MetricsCollector()
        if self.eunomia.enabled:
            print(f"  Eunomia: enabled (url={self.eunomia.url}, "
                  f"sim≥{self.eunomia.sim_threshold})")
        else:
            print("  Eunomia: disabled (set EUNOMIA_URL to enable metadata cache)")

    def _build_source_map(self):
        """Build a mapping from source names to AstraeaDB node IDs."""
        with open(config.METADATA_DIR / "sources.json") as f:
            sources = json.load(f)
        id_map_path = config.METADATA_DIR / "id_map.json"
        if id_map_path.exists():
            with open(id_map_path) as f:
                id_map = json.load(f)
            for src in sources:
                name = src["properties"]["name"]
                node_id = id_map.get(src["id"])
                if node_id is not None:
                    self._source_node_map[name] = node_id

    def _load_id_map_from_file(self):
        """Load source map from files when AstraeaDB is unavailable."""
        id_map_path = config.METADATA_DIR / "id_map.json"
        sources_path = config.METADATA_DIR / "sources.json"
        if id_map_path.exists() and sources_path.exists():
            with open(id_map_path) as f:
                id_map = json.load(f)
            with open(sources_path) as f:
                sources = json.load(f)
            for src in sources:
                name = src["properties"]["name"]
                node_id = id_map.get(src["id"])
                if node_id is not None:
                    self._source_node_map[name] = node_id

    # --- Tool execution ---

    def execute_tool(self, name: str, arguments: dict) -> str:
        """Execute a tool call and return the result as a string."""
        if name == "list_data_sources":
            return tool_list_data_sources()

        elif name == "preview_data_source":
            return tool_preview_data_source(
                arguments["source_name"],
                arguments.get("n_rows", 5),
            )

        elif name == "query_data_source":
            return tool_query_data_source(
                arguments["source_name"],
                arguments["sql"],
                arguments.get("limit", 100),
            )

        elif name == "search_catalog":
            query_text = arguments["query"]
            k = arguments.get("k", 10)
            # Embed the query. If Ollama is down we skip the cache entirely
            # (without an embedding there's nothing to key the cache on) and
            # fall straight to the all-sources fallback.
            try:
                query_vec = embed_text(query_text)
            except Exception as e:
                return self._search_catalog_fallback(error=f"embedding: {e}")

            # Semantic cache check — a hit here means a prior query with a
            # semantically-similar embedding has been answered already.
            t0 = time.perf_counter()
            cached = self.eunomia.recall_semantic(
                query_vec, min_k=k, tag="search_catalog"
            )
            if cached is not None:
                self.metrics.record(
                    "search_catalog", True, "eunomia",
                    (time.perf_counter() - t0) * 1000,
                )
                return cached

            # Miss: try AstraeaDB; on failure, use the all-sources fallback.
            # Either path takes a "miss"-shaped sample so the report reflects
            # what the LLM would have paid without the cache.
            t0 = time.perf_counter()
            try:
                if self.db is None:
                    raise RuntimeError("AstraeaDB unavailable")
                results = self.db.vector_search(query_vec, k=k)
                result_str = json.dumps(results, indent=2, default=str)
            except Exception as e:
                result_str = self._search_catalog_fallback(error=str(e))
            self.metrics.record(
                "search_catalog", False, "astraea",
                (time.perf_counter() - t0) * 1000,
            )
            cache_id = "sc:" + hashlib.sha1(query_text.encode()).hexdigest()[:16]
            self.eunomia.store_semantic(
                cache_id, query_vec, result_str, k=k, tag="search_catalog",
            )
            return result_str

        elif name == "get_source_details":
            return self._get_source_details(arguments["source_name"])

        elif name == "find_related_sources":
            return self._find_related_sources(arguments["source_name"])

        else:
            return json.dumps({"error": f"Unknown tool: {name}"})

    def _search_catalog_fallback(self, *, error: str) -> str:
        """Return all source metadata when AstraeaDB / Ollama isn't reachable."""
        try:
            with open(config.METADATA_DIR / "sources.json") as f:
                sources = json.load(f)
            fallback = []
            for src in sources:
                p = src["properties"]
                fallback.append({
                    "name": p["name"],
                    "description": p.get("description", "")[:300],
                    "format": p["format"],
                    "active_from": p.get("active_from"),
                    "active_to": p.get("active_to"),
                })
            return json.dumps({
                "note": f"Semantic search unavailable ({error}). Returning all sources for manual review.",
                "sources": fallback,
            }, indent=2, default=str)
        except Exception:
            return json.dumps({"error": f"Catalog search failed: {error}. Use list_data_sources instead."})

    def _get_source_details(self, source_name: str) -> str:
        """Get full details about a data source. Cache-fronted by Eunomia."""
        cache_key = f"src_details:{source_name}"
        t0 = time.perf_counter()
        cached = self.eunomia.get_exact(cache_key)
        if cached is not None:
            self.metrics.record(
                "get_source_details", True, "eunomia",
                (time.perf_counter() - t0) * 1000,
            )
            return cached

        t0 = time.perf_counter()
        result = self._compute_source_details(source_name)
        self.metrics.record(
            "get_source_details", False, "astraea",
            (time.perf_counter() - t0) * 1000,
        )
        self.eunomia.store_exact(cache_key, result, tags=["get_source_details"])
        return result

    def _compute_source_details(self, source_name: str) -> str:
        """Compute source details from the metadata graph (or the file fallback)."""
        node_id = self._source_node_map.get(source_name)

        # Try AstraeaDB first
        if node_id is not None and self.db is not None:
            try:
                node = self.db.get_node(node_id)
                neighbors = self.db.neighbors(node_id, direction="outgoing")

                fields = []
                for n in neighbors:
                    if isinstance(n, dict):
                        edge_type = n.get("edge_type", "")
                        if edge_type == "HAS_FIELD":
                            target_id = n.get("target") or n.get("node_id")
                            if target_id:
                                field_node = self.db._get_node_cached(target_id)
                                fields.append(field_node.get("properties", {}))

                result = {
                    "source": node.get("properties", {}),
                    "fields": fields,
                }
                return json.dumps(result, indent=2, default=str)
            except Exception:
                pass  # Fall through to metadata file fallback

        # Fallback: read from metadata files directly
        return self._get_source_details_from_files(source_name)

    def _get_source_details_from_files(self, source_name: str) -> str:
        """Fallback: get source details from the metadata JSON files."""
        try:
            with open(config.METADATA_DIR / "sources.json") as f:
                sources = json.load(f)
            with open(config.METADATA_DIR / "fields.json") as f:
                all_fields = json.load(f)

            source = None
            source_id = None
            for src in sources:
                if src["properties"]["name"] == source_name:
                    source = src["properties"]
                    source_id = src["id"]
                    break

            if source is None:
                return json.dumps({"error": f"Source '{source_name}' not found. Use list_data_sources to see available sources."})

            # Find fields belonging to this source
            fields = []
            for field in all_fields:
                if field.get("source") == source_id or field.get("source_id") == source_id:
                    fields.append(field.get("properties", field))

            return json.dumps({"source": source, "fields": fields}, indent=2, default=str)
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _find_related_sources(self, source_name: str) -> str:
        """Find sources related to ``source_name``. Cache-fronted by Eunomia."""
        cache_key = f"src_related:{source_name}"
        t0 = time.perf_counter()
        cached = self.eunomia.get_exact(cache_key)
        if cached is not None:
            self.metrics.record(
                "find_related_sources", True, "eunomia",
                (time.perf_counter() - t0) * 1000,
            )
            return cached

        t0 = time.perf_counter()
        result = self._compute_related_sources(source_name)
        self.metrics.record(
            "find_related_sources", False, "astraea",
            (time.perf_counter() - t0) * 1000,
        )
        self.eunomia.store_exact(cache_key, result, tags=["find_related_sources"])
        return result

    def _compute_related_sources(self, source_name: str) -> str:
        """Compute related sources from the graph (or the file fallback)."""
        node_id = self._source_node_map.get(source_name)

        # Try AstraeaDB first
        if node_id is not None and self.db is not None:
            try:
                neighbors = self.db.neighbors(node_id, direction="both")
                related = []
                for n in neighbors:
                    if isinstance(n, dict):
                        edge_type = n.get("edge_type", "")
                        if edge_type in ("SUCCEEDED_BY", "OVERLAPS_WITH", "BELONGS_TO_DOMAIN"):
                            target_id = n.get("target") or n.get("source") or n.get("node_id")
                            if target_id and target_id != node_id:
                                target_node = self.db._get_node_cached(target_id)
                                related.append({
                                    "relationship": edge_type,
                                    "properties": n.get("properties", {}),
                                    "related_source": target_node.get("properties", {}),
                                })
                return json.dumps(related, indent=2, default=str)
            except Exception:
                pass  # Fall through to metadata file fallback

        # Fallback: read relationships from edges.json
        return self._find_related_from_files(source_name)

    def _find_related_from_files(self, source_name: str) -> str:
        """Fallback: find related sources from the metadata JSON files."""
        try:
            with open(config.METADATA_DIR / "sources.json") as f:
                sources = json.load(f)
            with open(config.METADATA_DIR / "edges.json") as f:
                edges = json.load(f)

            # Find source ID
            source_id = None
            source_map = {}
            for src in sources:
                source_map[src["id"]] = src["properties"]
                if src["properties"]["name"] == source_name:
                    source_id = src["id"]

            if source_id is None:
                return json.dumps({"error": f"Source '{source_name}' not found"})

            related = []
            for edge in edges:
                if edge.get("type") in ("SUCCEEDED_BY", "OVERLAPS_WITH"):
                    if edge.get("source") == source_id:
                        target_props = source_map.get(edge.get("target"), {})
                        if target_props:
                            related.append({
                                "relationship": edge["type"],
                                "properties": edge.get("properties", {}),
                                "related_source": target_props,
                            })
                    elif edge.get("target") == source_id:
                        src_props = source_map.get(edge.get("source"), {})
                        if src_props:
                            related.append({
                                "relationship": edge["type"] + " (incoming)",
                                "properties": edge.get("properties", {}),
                                "related_source": src_props,
                            })
            return json.dumps(related, indent=2, default=str)
        except Exception as e:
            return json.dumps({"error": str(e)})

    # --- LLM interaction ---

    def query_llm(self, question: str, show_tools: bool = True) -> str:
        """Send a question through the full discovery→query→synthesis pipeline."""
        if config.LLM_PROVIDER == "anthropic" and HAS_ANTHROPIC:
            return self._query_anthropic(question, show_tools)
        elif HAS_HTTPX:
            return self._query_ollama(question, show_tools)
        else:
            return "ERROR: No LLM provider available. Set LLM_PROVIDER and install dependencies."

    @staticmethod
    def _anthropic_call_with_retry(client, messages, max_retries=5):
        """Call the Anthropic API with exponential backoff on overloaded errors."""
        for attempt in range(max_retries):
            try:
                return client.messages.create(
                    model=config.ANTHROPIC_MODEL,
                    max_tokens=4096,
                    system=SYSTEM_PROMPT,
                    tools=TOOL_DEFINITIONS,
                    messages=messages,
                )
            except anthropic.OverloadedError:
                wait = 2 ** attempt
                print(f"  (API overloaded, retrying in {wait}s...)")
                time.sleep(wait)
            except anthropic.RateLimitError:
                wait = 2 ** attempt
                print(f"  (Rate limited, retrying in {wait}s...)")
                time.sleep(wait)
        # Final attempt without catching
        return client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

    def _query_anthropic(self, question: str, show_tools: bool) -> str:
        """Query using Claude via the Anthropic API."""
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

        messages = [{"role": "user", "content": question}]

        for round_num in range(config.MAX_TOOL_ROUNDS):
            response = self._anthropic_call_with_retry(client, messages)

            # Check if model wants to use tools
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            text_blocks = [b for b in response.content if b.type == "text"]

            if not tool_uses:
                # No more tools — return the text response
                return "\n".join(b.text for b in text_blocks)

            # Process tool calls
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for tool_use in tool_uses:
                if show_tools:
                    display.tool_call(tool_use.name, json.dumps(tool_use.input, default=str)[:120])

                result = self.execute_tool(tool_use.name, tool_use.input)

                if show_tools:
                    # Show a brief summary of the result
                    try:
                        parsed = json.loads(result)
                        if isinstance(parsed, list):
                            display.result_summary(f"{len(parsed)} results")
                        elif isinstance(parsed, dict) and "row_count" in parsed:
                            display.result_summary(f"{parsed['row_count']} rows, {len(parsed.get('columns', []))} columns")
                        elif isinstance(parsed, dict) and "error" in parsed:
                            display.result_summary(f"Error: {parsed['error'][:80]}")
                    except Exception:
                        pass

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": result,
                })

            messages.append({"role": "user", "content": tool_results})

            # If we're approaching the limit, force the model to synthesize
            if round_num >= config.MAX_TOOL_ROUNDS - 2:
                messages.append({
                    "role": "user",
                    "content": (
                        "You are running low on tool rounds. Please synthesize "
                        "a final answer now using the data you have already collected. "
                        "Do NOT make any more tool calls — just provide your analysis "
                        "and answer in plain text."
                    ),
                })

        # Last-resort: one final call with tools disabled to force a text answer
        messages.append({
            "role": "user",
            "content": (
                "Please provide your best answer now based on all the information "
                "gathered above. Summarize your findings."
            ),
        })
        try:
            response = client.messages.create(
                model=config.ANTHROPIC_MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=messages,
                # No tools parameter = model can only produce text
            )
            text_blocks = [b for b in response.content if b.type == "text"]
            if text_blocks:
                return "\n".join(b.text for b in text_blocks)
        except Exception:
            pass

        return "Unable to complete the analysis. Please try a more specific question."

    def _query_ollama(self, question: str, show_tools: bool) -> str:
        """Query using Ollama with native tool calling."""
        # Convert Anthropic-style tool definitions to Ollama/OpenAI format
        ollama_tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            }
            for t in TOOL_DEFINITIONS
        ]

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]

        for round_num in range(config.MAX_TOOL_ROUNDS):
            response = httpx.post(
                f"{config.OLLAMA_URL}/api/chat",
                json={
                    "model": config.OLLAMA_CHAT_MODEL,
                    "messages": messages,
                    "tools": ollama_tools,
                    "stream": False,
                },
                timeout=600.0,
            )
            response.raise_for_status()
            msg = response.json()["message"]

            tool_calls = msg.get("tool_calls")
            if not tool_calls:
                return (msg.get("content") or "").strip() or "No response generated."

            # Append the assistant message (with tool_calls) to the conversation
            messages.append(msg)

            # Execute each tool call and append results
            for tc in tool_calls:
                fn = tc["function"]
                tool_name = fn["name"]
                tool_args = fn.get("arguments", {})

                if show_tools:
                    display.tool_call(tool_name, json.dumps(tool_args, default=str)[:120])

                result = self.execute_tool(tool_name, tool_args)

                if show_tools:
                    try:
                        parsed = json.loads(result)
                        if isinstance(parsed, list):
                            display.result_summary(f"{len(parsed)} results")
                        elif isinstance(parsed, dict) and "row_count" in parsed:
                            display.result_summary(f"{parsed['row_count']} rows, {len(parsed.get('columns', []))} columns")
                        elif isinstance(parsed, dict) and "error" in parsed:
                            display.result_summary(f"Error: {parsed['error'][:80]}")
                    except Exception:
                        pass

                messages.append({"role": "tool", "content": result})

            # If approaching the limit, nudge the model to synthesize
            if round_num >= config.MAX_TOOL_ROUNDS - 2:
                messages.append({
                    "role": "user",
                    "content": (
                        "You are running low on tool rounds. Please synthesize "
                        "a final answer now using the data you have already collected. "
                        "Do NOT make any more tool calls."
                    ),
                })

        # Final attempt without tools to force a text answer
        messages.append({
            "role": "user",
            "content": "Please provide your best answer now based on all the information gathered.",
        })
        try:
            response = httpx.post(
                f"{config.OLLAMA_URL}/api/chat",
                json={
                    "model": config.OLLAMA_CHAT_MODEL,
                    "messages": messages,
                    "stream": False,
                },
                timeout=600.0,
            )
            response.raise_for_status()
            reply = (response.json()["message"].get("content") or "").strip()
            if reply:
                return reply
        except Exception:
            pass

        return "Unable to complete the analysis. Please try a more specific question."

    # --- Narrated Demo ---

    def act1_fragmented_lake(self):
        """Act 1: The Fragmented Lake — establish the problem."""
        display.banner("ACT 1: The Fragmented Lake")

        display.narrate(
            "Imagine you're an analyst at AcmeCorp, a mid-size technology company. "
            "Over the years, your company has accumulated data across dozens of systems. "
            "Teams came and went, platforms were migrated, but the data stayed. "
            "Let's look at what's in your data lake today."
        )

        # Show data lake contents
        sources = self.duckdb.list_sources()
        display.source_tree([
            {**s, "file_path": s["file_path"].replace(str(config.PROJECT_DIR) + "/", "")}
            for s in sources
        ])

        # Show source metadata
        with open(config.METADATA_DIR / "sources.json") as f:
            source_meta = json.load(f)

        display.narrate(
            "Eight data sources. Three different file formats. Four different "
            "business domains. Some sources overlap in time, others replaced "
            "each other when the company switched platforms."
        )

        # Show timeline
        timeline_data = []
        for src in source_meta:
            p = src["properties"]
            timeline_data.append({
                "name": p["name"],
                "active_from": p["active_from"],
                "active_to": p["active_to"],
                "format": p["format"],
            })
        display.timeline(timeline_data)

        display.narrate(
            "Now imagine your CEO asks: 'How has the number of video calls "
            "changed since the Pandemic?' You know the data is in here somewhere. "
            "But which files? What format? What are the column names? "
            "Do you grep through every file hoping to find something about "
            "video calls?"
        )

        if config.INTERACTIVE_PAUSE:
            display.pause()

        display.narrate(
            "This is where an intelligent metadata catalog changes everything. "
            "AstraeaDB stores semantic descriptions of every data source, every "
            "field, and the relationships between them — enabling an AI assistant "
            "to find and use data that you didn't even know was there."
        )

    def act2_intelligent_catalog(self):
        """Act 2: The Intelligent Catalog — temporal + multi-perspective."""
        display.banner("ACT 2: The Intelligent Catalog")

        # Question 1: Temporal succession
        display.sub_banner("Question 1: Temporal Succession")
        display.narrate(
            "Let's ask the question that stumped us before. Watch how the AI "
            "discovers the right data sources, understands the platform migration, "
            "and synthesizes an answer across both systems."
        )

        question1 = "How has the number of video calls changed since the Pandemic? Show me monthly trends."
        print(f'  User: "{question1}"\n')

        if config.INTERACTIVE_PAUSE:
            display.pause("Press Enter to send to AI...")

        answer1 = self.query_llm(question1)
        print(f"\n  Assistant: {answer1}")

        if config.INTERACTIVE_PAUSE:
            display.pause()

        # Question 2: Multi-perspective
        display.sub_banner("Question 2: Multi-Perspective Correlation")
        display.narrate(
            "Now let's look at the same user from multiple security perspectives. "
            "The AI needs to find that logon, HTTP, and email data all contain "
            "information about the same users."
        )

        question2 = (
            "Show me all activity for user U0001 on January 2, 2023. "
            "I want to see their logon sessions, web browsing, and email activity."
        )
        print(f'  User: "{question2}"\n')

        if config.INTERACTIVE_PAUSE:
            display.pause("Press Enter to send to AI...")

        answer2 = self.query_llm(question2)
        print(f"\n  Assistant: {answer2}")

        if config.INTERACTIVE_PAUSE:
            display.pause()

    def act3_cross_domain(self):
        """Act 3: Cross-Domain Intelligence — span all domains."""
        display.banner("ACT 3: Cross-Domain Intelligence")

        display.narrate(
            "For the finale, let's ask a question that spans all four domains. "
            "The AI must discover connections between security logs, communications, "
            "HR records, and project management — linking different identifier "
            "formats along the way."
        )

        question3 = (
            "What can you tell me about user U0001 across all of our systems? "
            "Check their security activity, communications, HR records, and project work."
        )
        print(f'  User: "{question3}"\n')

        if config.INTERACTIVE_PAUSE:
            display.pause("Press Enter to send to AI...")

        answer3 = self.query_llm(question3)
        print(f"\n  Assistant: {answer3}")

        if config.INTERACTIVE_PAUSE:
            display.pause()

    def recap(self):
        """Recap: summarize what happened."""
        display.banner("RECAP")

        display.narrate(
            "Without the intelligent metadata catalog, these questions are "
            "effectively unanswerable — not because the data doesn't exist, "
            "but because no one knows it's there."
        )

        display.narrate(
            "AstraeaDB stored semantic descriptions of every data source and field, "
            "connected related fields across systems through shared concepts, and "
            "enabled the AI to discover, understand, and query data across four "
            "different domains, three file formats, and eight separate data sources."
        )

        display.table(
            ["Metric", "Value"],
            [
                ["Data sources in lake", "8"],
                ["File formats", "3 (CSV, JSON/JSONL, Parquet)"],
                ["Business domains", "4 (Security, Comms, HR, PM)"],
                ["Total rows across sources", f"{sum(s['row_count'] for s in self.duckdb.list_sources()):,}"],
                ["Identifier formats bridged", "4 (UXXXX, email, EMP-XXXX, WKR-XXXX)"],
                ["Platform migrations tracked", "2 (Teams→Zoom, Legacy HR→Modern HCM)"],
            ],
        )

        display.narrate(
            "This is what intelligent storage looks like. Not just a place to put "
            "data, but a system that understands what the data means and helps "
            "you find answers you didn't know you could ask."
        )

    def run_interactive(self):
        """Interactive chat mode."""
        display.sub_banner("Interactive Mode")
        print("  Ask any question about the data lake. Type /quit to exit.\n")
        print("  Suggested questions:")
        print('    - "Which data sources contain information about the Engineering department?"')
        print('    - "What happened on the day with the most security events?"')
        print('    - "Compare employee meeting frequency before and after the pandemic"')
        print('    - "Find users who appear in both security and HR data"')
        print()

        while True:
            try:
                question = input("  > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n")
                break

            if not question:
                continue
            if question.lower() in ("/quit", "/exit", "/q"):
                break

            print()
            answer = self.query_llm(question)
            print(f"\n  {answer}\n")

    def run(self, mode: str = "full"):
        """Main entry point."""
        display.banner("AstraeaDB Data Lake Demo")
        display.narrate(
            "Demonstrating how AstraeaDB can serve as an intelligent metadata "
            "catalog for a fragmented enterprise data lake, enabling an AI "
            "assistant to discover, correlate, and query data across disparate sources."
        )

        if mode in ("full", "narrated"):
            self.act1_fragmented_lake()
            self.act2_intelligent_catalog()
            self.act3_cross_domain()
            self.recap()

        if mode in ("full", "interactive"):
            self.run_interactive()


def main():
    parser = argparse.ArgumentParser(description="Data Lake Demo Orchestrator")
    parser.add_argument(
        "--mode",
        choices=["full", "narrated", "interactive"],
        default="full",
        help="Demo mode: full (narrated + interactive), narrated only, or interactive only",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Pause between sections for presenter control",
    )
    args = parser.parse_args()

    if args.interactive:
        config.INTERACTIVE_PAUSE = True

    orchestrator = DemoOrchestrator()
    try:
        orchestrator.run(args.mode)
    finally:
        # Always print whatever metadata-call samples were collected, even on
        # KeyboardInterrupt during interactive chat — these are the numbers
        # that show the cache pulling its weight (or that say it never ran).
        report = orchestrator.metrics.report()
        if report:
            print(report)
        orchestrator.eunomia.close()


if __name__ == "__main__":
    main()
