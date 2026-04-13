#!/usr/bin/env python3
"""Ingest the metadata graph into AstraeaDB.

Creates all nodes (Domain, DataSource, Field, Concept) with embeddings,
then creates all edges (BELONGS_TO_DOMAIN, HAS_FIELD, MAPS_TO_CONCEPT,
SUCCEEDED_BY, OVERLAPS_WITH, SAME_ENTITY_AS, RELATES_TO).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

# Import AstraeaDB client
sys.path.insert(0, "/Users/jimharris/Documents/astraeadb/python")
from astraeadb import JsonClient


def load_json(filename):
    """Load a JSON file from the metadata directory."""
    with open(config.METADATA_DIR / filename) as f:
        return json.load(f)


def load_embeddings():
    """Load pre-computed embeddings."""
    path = config.METADATA_DIR / "embeddings.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    print("WARNING: No embeddings found. Run generate_embeddings.py first.")
    print("         Nodes will be created without embeddings.")
    return {}


def main():
    print("=" * 60)
    print("Metadata Ingestion into AstraeaDB")
    print("=" * 60)
    print(f"\nConnecting to AstraeaDB at {config.ASTRAEA_HOST}:{config.ASTRAEA_PORT}...")

    client = JsonClient(config.ASTRAEA_HOST, config.ASTRAEA_PORT)

    # Test connection
    try:
        client.connect()
        print(f"  Connected to AstraeaDB at {config.ASTRAEA_HOST}:{config.ASTRAEA_PORT}")
    except Exception as e:
        print(f"  ERROR: Cannot connect to AstraeaDB: {e}")
        print(f"  Make sure AstraeaDB is running: astraeadb serve --port {config.ASTRAEA_PORT}")
        sys.exit(1)

    embeddings = load_embeddings()

    # Track string_id → node_id mapping
    id_map = {}

    # --- Create Domain nodes ---
    print("\n--- Creating Domain nodes ---")
    domains = load_json("domains.json")
    for domain in domains:
        emb = embeddings.get(domain["id"])
        node_id = client.create_node(
            labels=domain["labels"],
            properties=domain["properties"],
            embedding=emb,
        )
        id_map[domain["id"]] = node_id
        print(f"  {domain['properties']['name']}: node {node_id}")

    # --- Create Concept nodes ---
    print("\n--- Creating Concept nodes ---")
    concepts = load_json("concepts.json")
    for concept in concepts:
        emb = embeddings.get(concept["id"])
        node_id = client.create_node(
            labels=concept["labels"],
            properties=concept["properties"],
            embedding=emb,
        )
        id_map[concept["id"]] = node_id
        print(f"  {concept['properties']['name']}: node {node_id}")

    # --- Create DataSource nodes ---
    print("\n--- Creating DataSource nodes ---")
    sources = load_json("sources.json")
    for source in sources:
        emb = embeddings.get(source["id"])
        node_id = client.create_node(
            labels=source["labels"],
            properties=source["properties"],
            embedding=emb,
        )
        id_map[source["id"]] = node_id
        print(f"  {source['properties']['name']}: node {node_id}")

    # --- Create Field nodes ---
    print("\n--- Creating Field nodes ---")
    fields = load_json("fields.json")
    field_count = 0
    for field in fields:
        emb = embeddings.get(field["id"])
        # Serialize complex avro_type to string for storage
        props = dict(field["properties"])
        if isinstance(props.get("avro_type"), (dict, list)):
            props["avro_type"] = json.dumps(props["avro_type"])
        if isinstance(props.get("sample_values"), list):
            props["sample_values"] = json.dumps(props["sample_values"])

        node_id = client.create_node(
            labels=["Field"],
            properties=props,
            embedding=emb,
        )
        id_map[field["id"]] = node_id
        field_count += 1
    print(f"  Created {field_count} Field nodes")

    # --- Create edges ---
    print("\n--- Creating edges ---")
    edges = load_json("edges.json")
    edge_counts = {}

    for edge in edges:
        source_id = id_map.get(edge["source"])
        target_id = id_map.get(edge["target"])

        if source_id is None or target_id is None:
            print(f"  WARNING: Skipping edge {edge['type']} "
                  f"{edge['source']} -> {edge['target']} (node not found)")
            continue

        props = edge.get("properties", {})

        client.create_edge(
            source=source_id,
            target=target_id,
            edge_type=edge["type"],
            properties=props if props else None,
        )

        edge_type = edge["type"]
        edge_counts[edge_type] = edge_counts.get(edge_type, 0) + 1

    for etype, count in sorted(edge_counts.items()):
        print(f"  {etype}: {count} edges")

    # --- Save ID map ---
    id_map_path = config.METADATA_DIR / "id_map.json"
    with open(id_map_path, "w") as f:
        json.dump(id_map, f, indent=2)
    print(f"\nSaved ID map ({len(id_map)} entries) to {id_map_path}")

    # --- Summary ---
    total_nodes = len(id_map)
    total_edges = sum(edge_counts.values())
    print(f"\n{'=' * 60}")
    print(f"Ingestion complete!")
    print(f"  Nodes: {total_nodes}")
    print(f"  Edges: {total_edges}")
    print(f"  Embeddings: {sum(1 for k in id_map if k in embeddings)}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
