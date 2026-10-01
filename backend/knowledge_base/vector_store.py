import json

from django.conf import settings
from django.db import connection

from .embeddings import EMBEDDING_DIMENSIONS


def _enabled() -> bool:
    return bool(getattr(settings, "PGVECTOR_ENABLED", False) and connection.vendor == "postgresql")


def store_chunk_vector(chunk_id: int, vector: list[float], model: str) -> bool:
    if not _enabled() or len(vector) != EMBEDDING_DIMENSIONS:
        return False
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO knowledge_base_vector (chunk_id, embedding, embedding_model)
            VALUES (%s, %s::vector, %s)
            ON CONFLICT (chunk_id) DO UPDATE
            SET embedding = EXCLUDED.embedding, embedding_model = EXCLUDED.embedding_model
            """,
            [json.dumps(vector), model],
        )
    return True


def search_chunk_vectors(vector: list[float], limit: int, model: str) -> list[tuple[int, float]]:
    if not _enabled() or len(vector) != EMBEDDING_DIMENSIONS:
        return []
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT chunk_id, 1 - (embedding <=> %s::vector) AS score
            FROM knowledge_base_vector
            WHERE embedding_model = %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            [json.dumps(vector), model, json.dumps(vector), limit],
        )
        return [(int(chunk_id), float(score)) for chunk_id, score in cursor.fetchall()]
