"""Tests for the local embeddings client (Phase 3 plan, sub-task 3 - revised
to fastembed/Hugging Face instead of OpenAI, no network calls in these tests)."""

import pytest

from app.modules.rag.embeddings import EmbeddingsClient


class _FakeEmbedder:
    def __init__(self, vectors: list) -> None:
        self._vectors = vectors
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list:
        self.calls.append(list(texts))
        return self._vectors


@pytest.mark.anyio
async def test_embed_returns_vectors_in_input_order() -> None:
    embedder = _FakeEmbedder([[0.1, 0.1], [0.2, 0.2]])
    client = EmbeddingsClient(embedder=embedder)

    vectors = await client.embed(["first", "second"])

    assert vectors == [[0.1, 0.1], [0.2, 0.2]]
    assert embedder.calls == [["first", "second"]]


@pytest.mark.anyio
async def test_embed_empty_input_never_touches_the_model() -> None:
    embedder = _FakeEmbedder([])
    client = EmbeddingsClient(embedder=embedder)

    assert await client.embed([]) == []
    assert embedder.calls == []


@pytest.mark.anyio
async def test_embed_coerces_non_float_vectors_to_plain_floats() -> None:
    class _NumpyLike:
        def __init__(self, values: list[float]) -> None:
            self._values = values

        def __iter__(self):
            return iter(self._values)

    embedder = _FakeEmbedder([_NumpyLike([0.5, 0.25])])
    client = EmbeddingsClient(embedder=embedder)

    vectors = await client.embed(["x"])

    assert vectors == [[0.5, 0.25]]
    assert all(isinstance(v, float) for v in vectors[0])
