from dataclasses import dataclass

from helpdesk.ai_privacy import sanitize_prompt
from .embeddings import cosine_similarity, embed_text
from .models import DocumentChunk
from .vector_store import search_chunk_vectors


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: int
    document_id: int
    title: str
    content: str
    score: float


def retrieve(query: str, limit: int = 5) -> list[RetrievedChunk]:
    query_embedding, model = embed_text(sanitize_prompt(query))
    if not query_embedding:
        return []

    vector_matches = search_chunk_vectors(query_embedding, limit, model)
    if vector_matches:
        scores = dict(vector_matches)
        chunks = DocumentChunk.objects.filter(
            id__in=scores,
            document__is_active=True,
        ).select_related("document")
        return sorted(
            [
                RetrievedChunk(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    title=chunk.document.title,
                    content=chunk.content,
                    score=scores[chunk.id],
                )
                for chunk in chunks
            ],
            key=lambda item: item.score,
            reverse=True,
        )

    results = []
    for chunk in DocumentChunk.objects.filter(
        document__is_active=True,
        embedding_model=model,
    ).select_related("document"):
        score = cosine_similarity(query_embedding, chunk.embedding)
        if score >= 0.2:
            results.append(
                RetrievedChunk(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    title=chunk.document.title,
                    content=chunk.content,
                    score=score,
                )
            )
    return sorted(results, key=lambda item: item.score, reverse=True)[:limit]
