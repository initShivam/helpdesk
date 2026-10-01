from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from rest_framework.exceptions import ValidationError

from io import StringIO
from unittest.mock import patch

import httpx
from ollama import ResponseError
from tenacity import stop_after_attempt, wait_none

from .embeddings import EmbeddingError, EmbeddingRetryableError, cosine_similarity, embed_text
from .models import Document, DocumentChunk
from .retrieval import retrieve
from .services import index_document, index_uploaded_file
from .vector_store import search_chunk_vectors


@override_settings(EMBEDDING_PROVIDER='local')
class KnowledgeBaseTests(TestCase):
    def test_uploaded_documents_reject_unsupported_or_oversized_files(self):
        with self.assertRaises(ValidationError):
            index_uploaded_file(SimpleUploadedFile("payload.exe", b"not allowed"))
        with self.assertRaises(ValidationError):
            index_uploaded_file(SimpleUploadedFile("large.txt", b"x" * (10 * 1024 * 1024 + 1)))

    def test_indexes_and_retrieves_relevant_chunks(self):
        index_document(
            title="Password reset guide",
            content="Reset a forgotten password from the account security page.",
        )
        index_document(
            title="Refund policy",
            content="Refunds are available within thirty days of payment.",
        )

        results = retrieve("I cannot reset my forgotten password")

        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0].title, "Password reset guide")

    def test_embeddings_are_persisted_and_cosine_similarity_is_used(self):
        document = index_document(
            title="Password reset guide",
            content="Reset a forgotten password from the account security page.",
        )

        document.refresh_from_db()
        chunk = document.chunks.get()
        self.assertTrue(document.embedding)
        self.assertEqual(document.embedding_model, "local-hash-fallback")
        self.assertTrue(chunk.embedding)
        self.assertGreater(cosine_similarity(chunk.embedding, chunk.embedding), 0.99)

    @patch("knowledge_base.embeddings.Client")
    @override_settings(
        EMBEDDING_PROVIDER="ollama",
        OLLAMA_BASE_URL="http://localhost:11434",
        OLLAMA_EMBEDDING_MODEL="nomic-embed-text",
    )
    def test_ollama_embedding_uses_configured_model_and_url(self, ollama_client):
        client = ollama_client.return_value
        vector = [0.1] * 768
        client.embed.return_value.embeddings = [vector]

        result, model = embed_text("password reset")

        self.assertEqual(len(result), 768)
        self.assertEqual(model, "ollama:nomic-embed-text")
        ollama_client.assert_called_once_with(
            host="http://localhost:11434",
            timeout=120,
        )
        client.embed.assert_called_once_with(model="nomic-embed-text", input="password reset")

    @patch("knowledge_base.embeddings.Client")
    @override_settings(EMBEDDING_PROVIDER="ollama")
    def test_rejects_embedding_with_wrong_dimensions(self, ollama_client):
        ollama_client.return_value.embed.return_value.embeddings = [[0.1] * 12]

        with self.assertRaisesRegex(EmbeddingError, "expected 768 dimensions"):
            embed_text("a query")

    @patch("knowledge_base.embeddings.Client")
    @override_settings(EMBEDDING_PROVIDER="ollama")
    def test_connection_failure_is_retryable(self, ollama_client):
        ollama_client.return_value.embed.side_effect = ConnectionError("connection refused")
        single_attempt = embed_text.retry_with(stop=stop_after_attempt(1), wait=wait_none())

        with self.assertRaises(EmbeddingRetryableError):
            single_attempt("a query")

    @patch("knowledge_base.embeddings.Client")
    @override_settings(EMBEDDING_PROVIDER="ollama")
    def test_timeout_is_retryable(self, ollama_client):
        ollama_client.return_value.embed.side_effect = httpx.ReadTimeout("timed out")
        single_attempt = embed_text.retry_with(stop=stop_after_attempt(1), wait=wait_none())

        with self.assertRaises(EmbeddingRetryableError):
            single_attempt("a query")

    @patch("knowledge_base.embeddings.Client")
    @override_settings(EMBEDDING_PROVIDER="ollama")
    def test_missing_ollama_model_is_reported_without_retry(self, ollama_client):
        ollama_client.return_value.embed.side_effect = ResponseError("model not found", status_code=404)

        with self.assertRaisesRegex(EmbeddingError, "ollama pull nomic-embed-text"):
            embed_text("a query")

    @patch("knowledge_base.retrieval.search_chunk_vectors", return_value=[])
    @patch("knowledge_base.retrieval.embed_text", return_value=([1.0] + [0.0] * 767, "ollama:nomic-embed-text"))
    def test_retrieval_never_mixes_openai_and_ollama_vectors(self, embed, search):
        old_document = Document.objects.create(title="Old", content="Old content")
        DocumentChunk.objects.create(
            document=old_document,
            content="matching old content",
            embedding=[1.0] + [0.0] * 767,
            embedding_model="text-embedding-3-small",
        )
        new_document = Document.objects.create(title="Current", content="Current content")
        DocumentChunk.objects.create(
            document=new_document,
            content="matching ollama content",
            embedding=[1.0] + [0.0] * 767,
            embedding_model="ollama:nomic-embed-text",
        )

        results = retrieve("matching content")

        self.assertEqual([item.title for item in results], ["Current"])
        search.assert_called_once_with([1.0] + [0.0] * 767, 5, "ollama:nomic-embed-text")

    @patch("knowledge_base.vector_store.connection")
    @patch("knowledge_base.vector_store._enabled", return_value=True)
    def test_pgvector_search_filters_by_embedding_model(self, enabled, db_connection):
        db_connection.cursor.return_value.__enter__.return_value.fetchall.return_value = []

        search_chunk_vectors([0.0] * 768, 5, "ollama:nomic-embed-text")

        sql, params = db_connection.cursor.return_value.__enter__.return_value.execute.call_args.args
        self.assertIn("WHERE embedding_model = %s", sql)
        self.assertIn("ollama:nomic-embed-text", params)

    @patch("knowledge_base.management.commands.reindex_embeddings.embed_text")
    @patch("knowledge_base.management.commands.reindex_embeddings.store_chunk_vector")
    @override_settings(EMBEDDING_PROVIDER="ollama", OLLAMA_EMBEDDING_MODEL="nomic-embed-text")
    def test_reindex_resumes_after_partial_failure(self, store_vector, embed):
        document = Document.objects.create(
            title="Guide",
            content="Guide content",
            embedding=[0.0] * 768,
            embedding_model="text-embedding-3-small",
        )
        first_chunk = DocumentChunk.objects.create(
            document=document,
            content="First part",
            position=0,
            embedding=[0.0] * 768,
            embedding_model="text-embedding-3-small",
        )
        second_chunk = DocumentChunk.objects.create(
            document=document,
            content="Second part",
            position=1,
            embedding=[0.0] * 768,
            embedding_model="text-embedding-3-small",
        )
        vector = [0.2] * 768
        embed.side_effect = [
            (vector, "ollama:nomic-embed-text"),
            (vector, "ollama:nomic-embed-text"),
            EmbeddingError("Ollama temporarily unavailable"),
        ]
        output = StringIO()

        with self.assertRaises(CommandError):
            call_command("reindex_embeddings", stdout=output)

        document.refresh_from_db()
        first_chunk.refresh_from_db()
        second_chunk.refresh_from_db()
        self.assertEqual(document.embedding_model, "ollama:nomic-embed-text")
        self.assertEqual(first_chunk.embedding_model, "ollama:nomic-embed-text")
        self.assertEqual(second_chunk.embedding_model, "text-embedding-3-small")

        embed.side_effect = [(vector, "ollama:nomic-embed-text")]
        call_command("reindex_embeddings", stdout=StringIO())

        second_chunk.refresh_from_db()
        self.assertEqual(second_chunk.embedding_model, "ollama:nomic-embed-text")
        self.assertEqual(embed.call_count, 4)
        store_vector.assert_any_call(first_chunk.pk, vector, "ollama:nomic-embed-text")

    @override_settings(EMBEDDING_PROVIDER="ollama")
    def test_indexing_stores_provider_metadata_for_document_and_chunks(self):
        vector = [0.2] * 768
        with patch("knowledge_base.services.embed_text", return_value=(vector, "ollama:nomic-embed-text")), patch(
            "knowledge_base.services.store_chunk_vector"
        ):
            document = index_document(title="Ollama guide", content="A single chunk of content.")

        chunk = document.chunks.get()
        self.assertEqual(document.embedding_model, "ollama:nomic-embed-text")
        self.assertEqual(chunk.embedding_model, "ollama:nomic-embed-text")

    def test_embedding_failure_does_not_create_partial_document(self):
        with patch(
            "knowledge_base.services.embed_text",
            side_effect=EmbeddingError("Ollama unavailable"),
        ):
            with self.assertRaises(EmbeddingError):
                index_document(title="Unavailable guide", content="Content to index")

        self.assertFalse(Document.objects.filter(title="Unavailable guide").exists())
