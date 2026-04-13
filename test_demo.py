"""Test suite for the Data Lake Demo.

Four-layer test pyramid:
  Layer 1: Data Integrity — verify all 8 data files exist and are valid
  Layer 2: AstraeaDB Metadata — verify graph is loaded correctly
  Layer 3: DuckDB Tools — verify data querying works
  Layer 4: End-to-End — verify full orchestrator pipeline
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import config


# ===========================================================================
# Layer 1: Data Integrity
# ===========================================================================

class TestDataIntegrity:
    """Verify all data files exist, are readable, and have expected structure."""

    def test_logon_events_exists(self):
        path = config.SECURITY_DIR / "logon_events.csv"
        assert path.exists(), f"Missing: {path}"
        assert path.stat().st_size > 0

    def test_http_access_exists(self):
        path = config.SECURITY_DIR / "http_access.jsonl"
        assert path.exists(), f"Missing: {path}"
        assert path.stat().st_size > 0

    def test_email_activity_exists(self):
        path = config.SECURITY_DIR / "email_activity.parquet"
        assert path.exists(), f"Missing: {path}"
        assert path.stat().st_size > 0

    def test_teams_calls_exists(self):
        path = config.COMMS_DIR / "teams_calls_2018_2021.csv"
        assert path.exists(), f"Missing: {path}"
        assert path.stat().st_size > 0

    def test_zoom_meetings_exists(self):
        path = config.COMMS_DIR / "zoom_meetings_2020_2024.json"
        assert path.exists(), f"Missing: {path}"
        assert path.stat().st_size > 0

    def test_legacy_hris_exists(self):
        path = config.HR_DIR / "legacy_hris_2017_2021.csv"
        assert path.exists(), f"Missing: {path}"
        assert path.stat().st_size > 0

    def test_modern_hcm_exists(self):
        path = config.HR_DIR / "modern_hcm_2021_2024.json"
        assert path.exists(), f"Missing: {path}"
        assert path.stat().st_size > 0

    def test_project_tickets_exists(self):
        path = config.PROJECTS_DIR / "project_tickets.parquet"
        assert path.exists(), f"Missing: {path}"
        assert path.stat().st_size > 0

    def test_csv_parses_correctly(self):
        import duckdb
        conn = duckdb.connect()
        count = conn.execute(
            f"SELECT COUNT(*) FROM read_csv_auto('{config.SECURITY_DIR}/logon_events.csv')"
        ).fetchone()[0]
        assert count > 1000, f"Expected >1000 logon rows, got {count}"

    def test_jsonl_parses_correctly(self):
        import duckdb
        conn = duckdb.connect()
        count = conn.execute(
            f"SELECT COUNT(*) FROM read_json_auto('{config.SECURITY_DIR}/http_access.jsonl')"
        ).fetchone()[0]
        assert count > 1000, f"Expected >1000 HTTP rows, got {count}"

    def test_parquet_parses_correctly(self):
        import duckdb
        conn = duckdb.connect()
        count = conn.execute(
            f"SELECT COUNT(*) FROM read_parquet('{config.SECURITY_DIR}/email_activity.parquet')"
        ).fetchone()[0]
        assert count > 1000, f"Expected >1000 email rows, got {count}"

    def test_json_array_parses_correctly(self):
        import duckdb
        conn = duckdb.connect()
        count = conn.execute(
            f"SELECT COUNT(*) FROM read_json_auto('{config.COMMS_DIR}/zoom_meetings_2020_2024.json')"
        ).fetchone()[0]
        assert count > 1000, f"Expected >1000 Zoom rows, got {count}"

    def test_teams_date_range(self):
        import duckdb
        conn = duckdb.connect()
        result = conn.execute(
            f"SELECT MIN(call_date), MAX(call_date) FROM read_csv_auto('{config.COMMS_DIR}/teams_calls_2018_2021.csv')"
        ).fetchone()
        assert "2018" in str(result[0]), f"Teams should start in 2018, got {result[0]}"
        assert "2021" in str(result[1]), f"Teams should end in 2021, got {result[1]}"

    def test_zoom_date_range(self):
        import duckdb
        conn = duckdb.connect()
        result = conn.execute(
            f"SELECT MIN(meeting_start), MAX(meeting_start) FROM read_json_auto('{config.COMMS_DIR}/zoom_meetings_2020_2024.json')"
        ).fetchone()
        assert "2020" in str(result[0]), f"Zoom should start in 2020, got {result[0]}"
        assert "2024" in str(result[1]), f"Zoom should end in 2024, got {result[1]}"

    def test_shared_users_across_security_sources(self):
        """Security sources should share user IDs."""
        import duckdb
        conn = duckdb.connect()
        logon_users = set(r[0] for r in conn.execute(
            f"SELECT DISTINCT user FROM read_csv_auto('{config.SECURITY_DIR}/logon_events.csv') LIMIT 50"
        ).fetchall())
        http_users = set(r[0] for r in conn.execute(
            f"SELECT DISTINCT user FROM read_json_auto('{config.SECURITY_DIR}/http_access.jsonl') LIMIT 50"
        ).fetchall())
        overlap = logon_users & http_users
        assert len(overlap) > 10, f"Expected shared users across security sources, got {len(overlap)}"


# ===========================================================================
# Layer 2: Metadata Files
# ===========================================================================

class TestMetadataFiles:
    """Verify metadata JSON files are valid and consistent."""

    def test_domains_json(self):
        with open(config.METADATA_DIR / "domains.json") as f:
            domains = json.load(f)
        assert len(domains) == 4
        names = {d["properties"]["name"] for d in domains}
        assert "Security" in names
        assert "Communications" in names

    def test_sources_json(self):
        with open(config.METADATA_DIR / "sources.json") as f:
            sources = json.load(f)
        assert len(sources) == 8
        formats = {s["properties"]["format"] for s in sources}
        assert "csv" in formats
        assert "json" in formats or "jsonl" in formats
        assert "parquet" in formats

    def test_fields_json(self):
        with open(config.METADATA_DIR / "fields.json") as f:
            fields = json.load(f)
        assert len(fields) > 50, f"Expected >50 fields, got {len(fields)}"
        # Every field has required properties
        for field in fields:
            assert "name" in field["properties"]
            assert "description" in field["properties"]
            assert "data_type" in field["properties"]

    def test_concepts_json(self):
        with open(config.METADATA_DIR / "concepts.json") as f:
            concepts = json.load(f)
        assert len(concepts) >= 15
        names = {c["properties"]["name"] for c in concepts}
        assert "User Identity" in names
        assert "Call / Meeting Duration" in names

    def test_edges_json(self):
        with open(config.METADATA_DIR / "edges.json") as f:
            edges = json.load(f)
        edge_types = {e["type"] for e in edges}
        assert "HAS_FIELD" in edge_types
        assert "MAPS_TO_CONCEPT" in edge_types
        assert "SUCCEEDED_BY" in edge_types
        assert "SAME_ENTITY_AS" in edge_types

    def test_edges_reference_valid_nodes(self):
        """All edge source/target IDs should exist in the node files."""
        all_ids = set()
        for filename in ["domains.json", "sources.json", "concepts.json"]:
            with open(config.METADATA_DIR / filename) as f:
                for item in json.load(f):
                    all_ids.add(item["id"])
        with open(config.METADATA_DIR / "fields.json") as f:
            for item in json.load(f):
                all_ids.add(item["id"])

        with open(config.METADATA_DIR / "edges.json") as f:
            edges = json.load(f)

        for edge in edges:
            assert edge["source"] in all_ids, f"Edge source '{edge['source']}' not found"
            assert edge["target"] in all_ids, f"Edge target '{edge['target']}' not found"

    def test_field_sources_match(self):
        """Every field's source should reference a valid DataSource."""
        with open(config.METADATA_DIR / "sources.json") as f:
            source_ids = {s["id"] for s in json.load(f)}
        with open(config.METADATA_DIR / "fields.json") as f:
            fields = json.load(f)
        for field in fields:
            assert field["source"] in source_ids, \
                f"Field '{field['id']}' references unknown source '{field['source']}'"


# ===========================================================================
# Layer 3: DuckDB Tools
# ===========================================================================

class TestDuckDbTools:
    """Verify data querying works correctly."""

    def test_list_sources(self):
        from src.duckdb_tools import get_tools
        tools = get_tools()
        sources = tools.list_sources()
        assert len(sources) == 8
        names = {s["name"] for s in sources}
        assert "CERT Logon Events" in names
        assert "Zoom Meeting Logs" in names

    def test_preview_csv(self):
        from src.duckdb_tools import get_tools
        tools = get_tools()
        preview = tools.preview("CERT Logon Events", n_rows=3)
        assert preview["row_count"] > 1000
        col_names = {c["name"] for c in preview["columns"]}
        assert "user" in col_names
        assert "activity" in col_names
        assert len(preview["sample_rows"]) == 3

    def test_preview_jsonl(self):
        from src.duckdb_tools import get_tools
        tools = get_tools()
        preview = tools.preview("Web Proxy HTTP Access Logs", n_rows=3)
        col_names = {c["name"] for c in preview["columns"]}
        assert "url" in col_names
        assert "user" in col_names

    def test_preview_parquet(self):
        from src.duckdb_tools import get_tools
        tools = get_tools()
        preview = tools.preview("Email Gateway Activity", n_rows=3)
        col_names = {c["name"] for c in preview["columns"]}
        assert "from_address" in col_names
        assert "has_attachments" in col_names

    def test_query_aggregation(self):
        from src.duckdb_tools import get_tools
        tools = get_tools()
        result = tools.query(
            "CERT Logon Events",
            "SELECT activity, COUNT(*) as cnt FROM data GROUP BY activity ORDER BY cnt DESC",
        )
        assert len(result) == 2  # Logon and Logoff
        activities = {r["activity"] for r in result}
        assert "Logon" in activities
        assert "Logoff" in activities

    def test_query_filter(self):
        from src.duckdb_tools import get_tools
        tools = get_tools()
        result = tools.query(
            "CERT Logon Events",
            "SELECT DISTINCT user FROM data WHERE user = 'U0001'",
        )
        assert len(result) == 1
        assert result[0]["user"] == "U0001"

    def test_cross_source_user_correlation(self):
        """The same user should be findable across security sources."""
        from src.duckdb_tools import get_tools
        tools = get_tools()

        logon = tools.query("CERT Logon Events",
                            "SELECT COUNT(*) as cnt FROM data WHERE user = 'U0001'")
        http = tools.query("Web Proxy HTTP Access Logs",
                           "SELECT COUNT(*) as cnt FROM data WHERE user = 'U0001'")
        email = tools.query("Email Gateway Activity",
                            "SELECT COUNT(*) as cnt FROM data WHERE user = 'U0001'")

        assert logon[0]["cnt"] > 0, "U0001 should appear in logon events"
        assert http[0]["cnt"] > 0, "U0001 should appear in HTTP access"
        assert email[0]["cnt"] > 0, "U0001 should appear in email activity"


# ===========================================================================
# Layer 4: End-to-End (requires AstraeaDB running)
# ===========================================================================

@pytest.mark.skipif(
    not (config.METADATA_DIR / "id_map.json").exists(),
    reason="AstraeaDB metadata not ingested (run 'make ingest' first)",
)
class TestEndToEnd:
    """End-to-end tests requiring AstraeaDB and Ollama."""

    def test_orchestrator_creates(self):
        from src.orchestrator import DemoOrchestrator
        orch = DemoOrchestrator()
        assert len(orch.duckdb.sources) == 8

    def test_duckdb_tool_functions(self):
        from src.duckdb_tools import tool_list_data_sources
        result = json.loads(tool_list_data_sources())
        assert len(result) == 8
