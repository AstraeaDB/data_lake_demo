"""DuckDB-backed data lake query tools.

Provides a unified SQL interface for querying data files in any supported
format (CSV, JSON, JSONL, Parquet). Each data source is registered with
its file path and format, and queries are executed via DuckDB.
"""

import json
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).parent.parent))
import config


class DuckDbTools:
    """Query engine for the data lake backed by DuckDB."""

    def __init__(self):
        self.conn = duckdb.connect()
        self.sources: dict[str, dict] = {}
        self._register_all_sources()

    def _register_all_sources(self):
        """Register all data sources from the metadata."""
        sources_path = config.METADATA_DIR / "sources.json"
        if not sources_path.exists():
            return

        with open(sources_path) as f:
            sources = json.load(f)

        for src in sources:
            props = src["properties"]
            self.register_source(
                name=props["name"],
                file_path=str(config.PROJECT_DIR / props["file_path"]),
                fmt=props["format"],
            )

    def register_source(self, name: str, file_path: str, fmt: str):
        """Register a data source for querying.

        Args:
            name: Human-readable name (e.g., "CERT Logon Events").
            file_path: Absolute path to the data file.
            fmt: File format ("csv", "json", "jsonl", "parquet").
        """
        self.sources[name] = {"path": file_path, "format": fmt}

    def _read_expression(self, source_name: str) -> str:
        """Get the DuckDB read expression for a source."""
        info = self.sources.get(source_name)
        if not info:
            raise ValueError(f"Unknown data source: '{source_name}'. "
                             f"Available: {list(self.sources.keys())}")

        path = info["path"]
        fmt = info["format"]

        if fmt == "csv":
            return f"read_csv_auto('{path}')"
        elif fmt in ("json", "jsonl"):
            return f"read_json_auto('{path}')"
        elif fmt == "parquet":
            return f"read_parquet('{path}')"
        else:
            raise ValueError(f"Unsupported format: {fmt}")

    def query(self, source_name: str, sql: str, limit: int = 100) -> list[dict]:
        """Execute a SQL query against a named data source.

        The query should reference the data as 'data'. For example:
            SELECT COUNT(*) FROM data WHERE user = 'U0042'

        Args:
            source_name: Name of the registered data source.
            sql: SQL query string (reference the source as 'data').
            limit: Maximum rows to return.

        Returns:
            List of dictionaries, one per result row.
        """
        read_expr = self._read_expression(source_name)

        # Strip trailing semicolons and check if user already included LIMIT
        sql_stripped = sql.strip().rstrip(";")
        if "limit" in sql_stripped.lower().split()[-2:]:
            full_sql = f"WITH data AS (SELECT * FROM {read_expr}) {sql_stripped}"
        else:
            full_sql = f"WITH data AS (SELECT * FROM {read_expr}) {sql_stripped} LIMIT {limit}"

        try:
            result = self.conn.execute(full_sql)
            columns = [desc[0] for desc in result.description]
            rows = result.fetchall()
            return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            return [{"error": str(e)}]

    def preview(self, source_name: str, n_rows: int = 5) -> dict:
        """Preview a data source: schema info and first N rows.

        Args:
            source_name: Name of the registered data source.
            n_rows: Number of sample rows to return.

        Returns:
            Dictionary with 'columns' (name + type) and 'sample_rows'.
        """
        read_expr = self._read_expression(source_name)

        # Get schema
        schema_result = self.conn.execute(
            f"DESCRIBE SELECT * FROM {read_expr}"
        )
        columns = []
        for row in schema_result.fetchall():
            columns.append({"name": row[0], "type": row[1]})

        # Get sample rows
        sample_result = self.conn.execute(
            f"SELECT * FROM {read_expr} LIMIT {n_rows}"
        )
        col_names = [desc[0] for desc in sample_result.description]
        rows = sample_result.fetchall()
        sample_rows = [dict(zip(col_names, row)) for row in rows]

        # Get row count
        count_result = self.conn.execute(
            f"SELECT COUNT(*) FROM {read_expr}"
        )
        row_count = count_result.fetchone()[0]

        source_info = self.sources[source_name]

        return {
            "source_name": source_name,
            "file_path": source_info["path"],
            "format": source_info["format"],
            "row_count": row_count,
            "columns": columns,
            "sample_rows": sample_rows,
        }

    def list_sources(self) -> list[dict]:
        """List all registered data sources with summary info.

        Returns:
            List of dictionaries with source name, format, path, and row count.
        """
        result = []
        for name, info in self.sources.items():
            try:
                read_expr = self._read_expression(name)
                count = self.conn.execute(
                    f"SELECT COUNT(*) FROM {read_expr}"
                ).fetchone()[0]
            except Exception:
                count = -1

            result.append({
                "name": name,
                "format": info["format"],
                "file_path": info["path"],
                "row_count": count,
            })
        return result


# --- Tool functions for the orchestrator ---

_tools_instance: DuckDbTools | None = None


def get_tools() -> DuckDbTools:
    """Get the singleton DuckDbTools instance."""
    global _tools_instance
    if _tools_instance is None:
        _tools_instance = DuckDbTools()
    return _tools_instance


def tool_query_data_source(source_name: str, sql: str, limit: int = 100) -> str:
    """MCP-compatible tool: query a data source with SQL.

    Args:
        source_name: Name of the data source to query.
        sql: SQL query (reference the table as 'data').
        limit: Max rows to return.

    Returns:
        JSON string of results.
    """
    tools = get_tools()
    result = tools.query(source_name, sql, limit)
    return json.dumps(result, indent=2, default=str)


def tool_preview_data_source(source_name: str, n_rows: int = 5) -> str:
    """MCP-compatible tool: preview a data source.

    Args:
        source_name: Name of the data source.
        n_rows: Number of sample rows.

    Returns:
        JSON string with schema and sample data.
    """
    tools = get_tools()
    result = tools.preview(source_name, n_rows)
    return json.dumps(result, indent=2, default=str)


def tool_list_data_sources() -> str:
    """MCP-compatible tool: list all available data sources.

    Returns:
        JSON string with source names, formats, and row counts.
    """
    tools = get_tools()
    result = tools.list_sources()
    return json.dumps(result, indent=2, default=str)
