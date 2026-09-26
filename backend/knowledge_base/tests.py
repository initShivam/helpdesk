from django.test import TestCase

from unittest.mock import patch

from .embeddings import cosine_similarity, embed_text
from .retrieval import retrieve
from .services import index_document


class KnowledgeBaseTests(TestCase):
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

    @patch("knowledge_base.embeddings.request.urlopen")
    @patch("knowledge_base.embeddings.settings.GEMINI_API_KEY", "test-key")
    def test_provider_embedding_is_used_when_configured(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = b'{"embedding":{"values":[0.1,0.2,0.3]}}'

        vector, model = embed_text("password reset")

        self.assertEqual(vector, [0.1, 0.2, 0.3])
        self.assertEqual(model, "text-embedding-004")
