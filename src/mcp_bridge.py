"""MCP bridge for communicating with AstraeaDB.

Launches AstraeaDB's MCP server as a subprocess and communicates via
JSON-RPC 2.0 over stdin/stdout. Enriches results with human-readable
node names and descriptions.

Based on the pattern from the GraphRAG demo.
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

# Also make AstraeaDB client available for direct calls
sys.path.insert(0, "/Users/jimharris/Documents/astraeadb/python")


class McpBridge:
    """Bridge to AstraeaDB via MCP (JSON-RPC 2.0 over stdio)."""

    def __init__(self):
        self.process: subprocess.Popen | None = None
        self._request_id = 0
        self._id_map: dict[str, int] = {}
        self._node_cache: dict[int, dict] = {}

    def start(self):
        """Start the AstraeaDB MCP server as a subprocess."""
        cmd = [
            config.ASTRAEA_BIN, "mcp",
            "--address", f"{config.ASTRAEA_HOST}:{config.ASTRAEA_PORT}",
        ]
        try:
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            # Read the initialization message
            self._read_response()
            print(f"  MCP bridge started (PID {self.process.pid})")
        except FileNotFoundError:
            print(f"  ERROR: Cannot find AstraeaDB binary at '{config.ASTRAEA_BIN}'")
            print(f"  Set ASTRAEA_BIN environment variable to the correct path")
            raise

    def stop(self):
        """Stop the MCP subprocess."""
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=5)
            self.process = None

    def load_id_map(self):
        """Load the string-ID to node-ID mapping."""
        path = config.METADATA_DIR / "id_map.json"
        if path.exists():
            with open(path) as f:
                self._id_map = json.load(f)

    def _send_request(self, method: str, params: dict | None = None) -> dict:
        """Send a JSON-RPC 2.0 request and return the result."""
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params or {},
        }

        if not self.process or self.process.poll() is not None:
            raise RuntimeError("MCP server is not running")

        line = json.dumps(request) + "\n"
        self.process.stdin.write(line)
        self.process.stdin.flush()

        return self._read_response()

    def _read_response(self) -> dict:
        """Read a JSON-RPC 2.0 response from the subprocess."""
        line = self.process.stdout.readline()
        if not line:
            stderr = self.process.stderr.read()
            raise RuntimeError(f"MCP server closed unexpectedly: {stderr}")
        return json.loads(line)

    # --- High-level tool methods ---

    def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Call an MCP tool and return the result.

        Args:
            tool_name: Name of the AstraeaDB MCP tool.
            arguments: Tool arguments as a dictionary.

        Returns:
            The tool result as a dictionary.
        """
        result = self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })

        if "error" in result:
            return {"error": result["error"]}

        # Extract the content from the MCP response
        content = result.get("result", {}).get("content", [])
        if content and isinstance(content, list):
            text = content[0].get("text", "")
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"text": text}

        return result.get("result", result)

    def find_by_label(self, label: str) -> list[dict]:
        """Find all nodes with a given label, enriched with names."""
        result = self.call_tool("find_by_label", {"label": label})
        if isinstance(result, dict) and "error" in result:
            return [result]

        # Enrich with node names
        if isinstance(result, list):
            enriched = []
            for item in result:
                node_id = item.get("id") or item.get("node_id")
                if node_id:
                    node = self._get_node_cached(node_id)
                    item["name"] = node.get("properties", {}).get("name", "")
                    item["description"] = node.get("properties", {}).get("description", "")[:200]
                enriched.append(item)
            return enriched
        return result if isinstance(result, list) else [result]

    def get_node(self, node_id: int) -> dict:
        """Get full node details by ID."""
        return self.call_tool("get_node", {"id": node_id})

    def neighbors(self, node_id: int, direction: str = "both",
                  edge_type: str | None = None) -> list[dict]:
        """Get neighbors of a node, enriched with names and edge types."""
        args = {"id": node_id, "direction": direction}
        if edge_type:
            args["edge_type"] = edge_type
        result = self.call_tool("neighbors", args)

        if isinstance(result, list):
            enriched = []
            for item in result:
                nid = item.get("id") or item.get("node_id")
                if nid:
                    node = self._get_node_cached(nid)
                    item["name"] = node.get("properties", {}).get("name", "")
                enriched.append(item)
            return enriched
        return result if isinstance(result, list) else [result]

    def vector_search(self, query_vector: list[float], k: int = 10) -> list[dict]:
        """Semantic search across all embedded nodes."""
        result = self.call_tool("vector_search", {"query": query_vector, "k": k})

        if isinstance(result, list):
            enriched = []
            for item in result:
                nid = item.get("id") or item.get("node_id")
                if nid:
                    node = self._get_node_cached(nid)
                    props = node.get("properties", {})
                    item["name"] = props.get("name", "")
                    item["labels"] = node.get("labels", [])
                    item["description"] = props.get("description", "")[:200]
                enriched.append(item)
            return enriched
        return result if isinstance(result, list) else [result]

    def hybrid_search(self, anchor: int, query_vector: list[float],
                      max_hops: int = 3, k: int = 10,
                      alpha: float = 0.5) -> list[dict]:
        """Blended graph proximity + vector similarity search."""
        result = self.call_tool("hybrid_search", {
            "anchor": anchor,
            "query": query_vector,
            "max_hops": max_hops,
            "k": k,
            "alpha": alpha,
        })

        if isinstance(result, list):
            enriched = []
            for item in result:
                nid = item.get("id") or item.get("node_id")
                if nid:
                    node = self._get_node_cached(nid)
                    props = node.get("properties", {})
                    item["name"] = props.get("name", "")
                    item["labels"] = node.get("labels", [])
                enriched.append(item)
            return enriched
        return result if isinstance(result, list) else [result]

    def gql_query(self, gql: str) -> dict:
        """Execute a GQL query."""
        return self.call_tool("query", {"gql": gql})

    def graph_stats(self) -> dict:
        """Get graph statistics."""
        return self.call_tool("graph_stats", {})

    def _get_node_cached(self, node_id: int) -> dict:
        """Get node details with caching."""
        if node_id not in self._node_cache:
            self._node_cache[node_id] = self.get_node(node_id)
        return self._node_cache[node_id]

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()


class DirectBridge:
    """Direct bridge to AstraeaDB using the JSON TCP client.

    Alternative to McpBridge that doesn't require the MCP subprocess.
    Uses the AstraeaDB Python client directly.
    """

    def __init__(self):
        from astraeadb import JsonClient
        self.client = JsonClient(config.ASTRAEA_HOST, config.ASTRAEA_PORT)
        self.client.connect()
        self._node_cache: dict[int, dict] = {}
        self._id_map: dict[str, int] = {}

    def load_id_map(self):
        """Load the string-ID to node-ID mapping."""
        path = config.METADATA_DIR / "id_map.json"
        if path.exists():
            with open(path) as f:
                self._id_map = json.load(f)

    def find_by_label(self, label: str) -> list[dict]:
        """Find all nodes with a given label."""
        result = self.client.query(
            f"MATCH (n:{label}) RETURN n"
        )
        return result if isinstance(result, list) else [result]

    def get_node(self, node_id: int) -> dict:
        """Get full node details."""
        return self.client.get_node(node_id)

    def neighbors(self, node_id: int, direction: str = "both",
                  edge_type: str | None = None) -> list[dict]:
        """Get neighbors of a node."""
        return self.client.neighbors(node_id, direction=direction,
                                     edge_type=edge_type)

    def vector_search(self, query_vector: list[float], k: int = 10) -> list[dict]:
        """Semantic search."""
        return self.client.vector_search(query_vector=query_vector, k=k)

    def hybrid_search(self, anchor: int, query_vector: list[float],
                      max_hops: int = 3, k: int = 10,
                      alpha: float = 0.5) -> list[dict]:
        """Hybrid search."""
        return self.client.hybrid_search(
            anchor=anchor, query_vector=query_vector,
            max_hops=max_hops, k=k, alpha=alpha,
        )

    def gql_query(self, gql: str) -> dict:
        """Execute a GQL query."""
        return self.client.query(gql)

    def _get_node_cached(self, node_id: int) -> dict:
        """Get node with caching."""
        if node_id not in self._node_cache:
            self._node_cache[node_id] = self.get_node(node_id)
        return self._node_cache[node_id]

    def start(self):
        """No-op for direct bridge (connection is immediate)."""
        pass

    def stop(self):
        """Close the client connection."""
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stop()
