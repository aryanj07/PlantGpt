"""RAG Module scaffold (plan Section H.2, D). Phase 3, owner: Prince."""

from dataclasses import dataclass


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    score: float
    source_uri: str


class RAGService:
    def retrieve(self, *, tenant_id: str, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        raise NotImplementedError("RAG retrieval lands in Phase 3 (plan Section H.2).")
