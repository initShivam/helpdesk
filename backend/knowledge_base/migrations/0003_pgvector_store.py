from django.db import migrations


def create_pgvector_store(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        try:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_base_vector (
                    chunk_id bigint PRIMARY KEY REFERENCES knowledge_base_documentchunk(id) ON DELETE CASCADE,
                    embedding vector(768) NOT NULL,
                    embedding_model varchar(100) NOT NULL DEFAULT ''
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS knowledge_base_vector_embedding_idx "
                "ON knowledge_base_vector USING hnsw (embedding vector_cosine_ops)"
            )
        except Exception:
            # Local PostgreSQL installations may not grant extension creation.
            # JSON storage remains the portable fallback in that environment.
            pass


class Migration(migrations.Migration):
    atomic = False
    dependencies = [
        ("knowledge_base", "0002_document_embedding_model_and_more"),
    ]
    operations = [migrations.RunPython(create_pgvector_store, migrations.RunPython.noop)]
