"""Embedding generation using Ollama's embeddinggemma model.

Follows the GraphRAG demo pattern: generate 768-dim embeddings via Ollama,
apply Matryoshka truncation to 128 dimensions, and L2-normalize.
"""

import math
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))
import config


def embed_text(text: str, model: str | None = None, dim: int | None = None) -> list[float]:
    """Generate an embedding for the given text.

    Args:
        text: The text to embed.
        model: Ollama model name (default: config.EMBEDDING_MODEL).
        dim: Target dimension after Matryoshka truncation (default: config.EMBEDDING_DIM).

    Returns:
        A list of floats representing the normalized embedding vector.
    """
    model = model or config.EMBEDDING_MODEL
    dim = dim or config.EMBEDDING_DIM

    url = f"{config.OLLAMA_URL}/api/embed"
    response = httpx.post(
        url,
        json={"model": model, "input": text},
        timeout=60.0,
    )
    response.raise_for_status()
    data = response.json()

    # Ollama returns {"embeddings": [[...]]} for /api/embed
    raw = data["embeddings"][0]

    # Matryoshka truncation: take first `dim` dimensions
    truncated = raw[:dim]

    # L2 normalize
    return _l2_normalize(truncated)


def embed_batch(texts: list[str], model: str | None = None, dim: int | None = None) -> list[list[float]]:
    """Generate embeddings for a batch of texts.

    Args:
        texts: List of texts to embed.
        model: Ollama model name.
        dim: Target dimension after truncation.

    Returns:
        List of normalized embedding vectors.
    """
    model = model or config.EMBEDDING_MODEL
    dim = dim or config.EMBEDDING_DIM

    url = f"{config.OLLAMA_URL}/api/embed"
    response = httpx.post(
        url,
        json={"model": model, "input": texts},
        timeout=120.0,
    )
    response.raise_for_status()
    data = response.json()

    results = []
    for raw in data["embeddings"]:
        truncated = raw[:dim]
        results.append(_l2_normalize(truncated))
    return results


def _l2_normalize(vec: list[float]) -> list[float]:
    """L2-normalize a vector to unit length."""
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]


def check_ollama_available() -> bool:
    """Check if Ollama is running and the embedding model is available."""
    try:
        resp = httpx.get(f"{config.OLLAMA_URL}/api/tags", timeout=5.0)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        # Check for model name (may include :latest tag)
        return any(config.EMBEDDING_MODEL in m for m in models)
    except Exception:
        return False
