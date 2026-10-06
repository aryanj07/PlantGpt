"""Local embeddings client (Phase 3 RAG). Revised from the original OpenAI
plan: runs BAAI/bge-small-en-v1.5 on-machine via fastembed (ONNX), a model
pulled from Hugging Face and cached locally after the first call - no API
key, no per-call cost, no network dependency once cached.
"""

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from app.config import Settings, get_settings

EMBEDDING_DIMENSIONS = 384  # BAAI/bge-small-en-v1.5's native output size

# Keep the ~65MB model weights off C: (same reasoning as the Android SDK/Gradle
# caches elsewhere in this project - C: is near-full on this machine) instead of
# fastembed's default %TEMP%, which also risks eviction by disk cleanup tools.
_CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "fastembed_cache"


class _Embedder(Protocol):
    def embed(self, texts: list[str]) -> Sequence[Sequence[float]]: ...


class EmbeddingsClient:
    def __init__(self, *, model_name: str = "BAAI/bge-small-en-v1.5", embedder: _Embedder | None = None) -> None:
        self._model_name = model_name
        self._embedder = embedder

    def _get_embedder(self) -> _Embedder:
        if self._embedder is None:
            from fastembed import TextEmbedding  # heavy import (loads the model) - deferred until first use

            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            self._embedder = TextEmbedding(model_name=self._model_name, cache_dir=str(_CACHE_DIR))
        return self._embedder

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []

        embedder = self._get_embedder()

        def _run() -> list[list[float]]:
            # fastembed preserves input order; coerce numpy arrays (or any
            # iterable of numbers) to plain floats for JSON/pgvector use.
            return [[float(x) for x in vector] for vector in embedder.embed(list(texts))]

        return await asyncio.to_thread(_run)


def get_embeddings_client(settings: Settings | None = None) -> EmbeddingsClient:
    settings = settings or get_settings()
    return EmbeddingsClient(model_name=settings.embedding_model)
