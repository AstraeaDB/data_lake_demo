#!/usr/bin/env python3
"""Generate embeddings for all metadata node descriptions.

Reads the metadata JSON files (domains, sources, fields, concepts),
generates embeddings for each node's description using Ollama embeddinggemma,
and writes the results to metadata/embeddings.json.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from src.embeddings import check_ollama_available, embed_batch, embed_text


def load_metadata():
    """Load all metadata nodes and collect their descriptions."""
    nodes = []

    for filename in ["domains.json", "sources.json", "concepts.json"]:
        path = config.METADATA_DIR / filename
        with open(path) as f:
            items = json.load(f)
        for item in items:
            nodes.append({
                "id": item["id"],
                "text": item["properties"]["description"],
            })

    # Fields: embed the description
    with open(config.METADATA_DIR / "fields.json") as f:
        fields = json.load(f)
    for field in fields:
        nodes.append({
            "id": field["id"],
            "text": field["properties"]["description"],
        })

    return nodes


def main():
    print("=" * 60)
    print("Embedding Generation")
    print("=" * 60)

    if not check_ollama_available():
        print(f"\nERROR: Ollama is not running or model '{config.EMBEDDING_MODEL}' is not available.")
        print(f"Please start Ollama and pull the model:")
        print(f"  ollama pull {config.EMBEDDING_MODEL}")
        sys.exit(1)

    nodes = load_metadata()
    print(f"\nGenerating embeddings for {len(nodes)} nodes...")
    print(f"  Model: {config.EMBEDDING_MODEL}")
    print(f"  Raw dimensions: {config.EMBEDDING_DIM_RAW}")
    print(f"  Truncated dimensions: {config.EMBEDDING_DIM}")

    embeddings = {}
    batch_size = 20

    for i in range(0, len(nodes), batch_size):
        batch = nodes[i : i + batch_size]
        texts = [n["text"] for n in batch]
        vectors = embed_batch(texts)

        for node, vec in zip(batch, vectors):
            embeddings[node["id"]] = vec

        done = min(i + batch_size, len(nodes))
        print(f"  [{done}/{len(nodes)}] embedded")

    # Save embeddings
    output_path = config.METADATA_DIR / "embeddings.json"
    with open(output_path, "w") as f:
        json.dump(embeddings, f)
    print(f"\nSaved {len(embeddings)} embeddings to {output_path}")

    # Verify dimensions
    sample = next(iter(embeddings.values()))
    print(f"  Dimension: {len(sample)}")
    norm = sum(x * x for x in sample) ** 0.5
    print(f"  L2 norm (should be ~1.0): {norm:.6f}")


if __name__ == "__main__":
    main()
