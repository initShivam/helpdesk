from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from knowledge_base.embeddings import (
    EMBEDDING_DIMENSIONS,
    EmbeddingError,
    configured_embedding_model,
    embed_text,
)
from knowledge_base.models import Document, DocumentChunk
from knowledge_base.vector_store import store_chunk_vector


class Command(BaseCommand):
    help = "Re-embed knowledge-base documents and chunks with the configured Ollama model."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Regenerate vectors that already use the configured Ollama model.",
        )

    @staticmethod
    def _is_current(embedding, embedding_model, target_model):
        return (
            embedding_model == target_model
            and isinstance(embedding, list)
            and len(embedding) == EMBEDDING_DIMENSIONS
        )

    def handle(self, *args, **options):
        if getattr(settings, "EMBEDDING_PROVIDER", "ollama").strip().lower() != "ollama":
            raise CommandError("Set EMBEDDING_PROVIDER=ollama before reindexing knowledge-base vectors.")

        try:
            target_model = configured_embedding_model()
        except EmbeddingError as exc:
            raise CommandError(str(exc)) from exc

        force = options["force"]
        updated_documents = 0
        skipped_documents = 0
        updated_chunks = 0
        skipped_chunks = 0

        try:
            for document in Document.objects.only("id", "content", "embedding", "embedding_model").iterator(chunk_size=50):
                if not force and self._is_current(
                    document.embedding,
                    document.embedding_model,
                    target_model,
                ):
                    skipped_documents += 1
                    continue

                vector, model = embed_text(document.content)
                if model != target_model or len(vector) != EMBEDDING_DIMENSIONS:
                    raise EmbeddingError("Ollama returned an embedding with unexpected model or dimensions.")
                with transaction.atomic():
                    Document.objects.filter(pk=document.pk).update(
                        embedding=vector,
                        embedding_model=model,
                    )
                updated_documents += 1

            for chunk in DocumentChunk.objects.only(
                "id", "content", "embedding", "embedding_model"
            ).iterator(chunk_size=100):
                if not force and self._is_current(
                    chunk.embedding,
                    chunk.embedding_model,
                    target_model,
                ):
                    skipped_chunks += 1
                    continue

                vector, model = embed_text(chunk.content)
                if model != target_model or len(vector) != EMBEDDING_DIMENSIONS:
                    raise EmbeddingError("Ollama returned an embedding with unexpected model or dimensions.")
                with transaction.atomic():
                    DocumentChunk.objects.filter(pk=chunk.pk).update(
                        embedding=vector,
                        embedding_model=model,
                    )
                    store_chunk_vector(chunk.pk, vector, model)
                updated_chunks += 1
        except EmbeddingError as exc:
            raise CommandError(
                "Reindex paused after "
                f"{updated_documents} documents and {updated_chunks} chunks; "
                f"rerun the command to resume safely. {exc}"
            ) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Reindex complete for {target_model}: "
                f"updated {updated_documents} documents/{updated_chunks} chunks; "
                f"skipped {skipped_documents} documents/{skipped_chunks} current chunks."
            )
        )
