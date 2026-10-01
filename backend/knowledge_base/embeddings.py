import hashlib
import logging
import math

import httpx
from django.conf import settings
from ollama import Client, ResponseError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from helpdesk.ai_privacy import sanitize_prompt


logger = logging.getLogger(__name__)
EMBEDDING_DIMENSIONS = 768
LOCAL_EMBEDDING_MODEL = "local-hash-fallback"


class EmbeddingError(Exception):
    """Raised when an embedding provider cannot return a usable vector."""


class EmbeddingConfigurationError(EmbeddingError):
    """Raised for provider configuration and missing-model problems."""


class EmbeddingRetryableError(EmbeddingError):
    """Raised for temporary embedding provider failures."""


def _local_embedding(text: str, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    """Stable explicitly selected offline fallback used in development and tests."""
    vector = [0.0] * dimensions
    for token in text.lower().split():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        vector[index] += 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [round(value / norm, 8) for value in vector]


def configured_embedding_model() -> str:
    provider = getattr(settings, "EMBEDDING_PROVIDER", "ollama").strip().lower()
    if provider == "local":
        return LOCAL_EMBEDDING_MODEL
    if provider != "ollama":
        raise EmbeddingConfigurationError(
            f"Unsupported embedding provider '{provider}'. Use 'ollama' or 'local'."
        )
    return f"ollama:{getattr(settings, 'OLLAMA_EMBEDDING_MODEL', 'nomic-embed-text')}"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(EmbeddingRetryableError),
    reraise=True,
)
def embed_text(text: str) -> tuple[list[float], str]:
    """Return a 768-dimensional vector and provider-qualified model identifier."""
    text = sanitize_prompt(text)
    provider = getattr(settings, "EMBEDDING_PROVIDER", "ollama").strip().lower()

    if provider == "local":
        return _local_embedding(text), LOCAL_EMBEDDING_MODEL
    if provider != "ollama":
        raise EmbeddingConfigurationError(
            f"Unsupported embedding provider '{provider}'. Use 'ollama' or 'local'."
        )

    model = getattr(settings, "OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
    model_id = f"ollama:{model}"
    base_url = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
    timeout = getattr(settings, "OLLAMA_TIMEOUT_SECONDS", 120)
    client = Client(host=base_url, timeout=timeout)

    try:
        response = client.embed(model=model, input=text)
        embeddings = response.embeddings
        vector = [float(value) for value in embeddings[0]]
        if len(vector) != EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"expected {EMBEDDING_DIMENSIONS} dimensions, received {len(vector)}"
            )
        return vector, model_id
    except ResponseError as exc:
        if exc.status_code == 404:
            logger.error("ollama_embedding_model_missing model=%s", model)
            raise EmbeddingConfigurationError(
                f"Ollama model '{model}' is not available. Install it with 'ollama pull {model}'."
            ) from exc
        if exc.status_code == 429 or exc.status_code >= 500:
            logger.warning(
                "ollama_embedding_provider_error model=%s status=%s retryable=true",
                model,
                exc.status_code,
            )
            raise EmbeddingRetryableError(
                f"Ollama embedding service temporarily unavailable (HTTP {exc.status_code})."
            ) from exc
        logger.error(
            "ollama_embedding_provider_error model=%s status=%s retryable=false",
            model,
            exc.status_code,
        )
        raise EmbeddingError(
            f"Ollama rejected the embedding request (HTTP {exc.status_code})."
        ) from exc
    except (ConnectionError, httpx.TimeoutException, TimeoutError) as exc:
        logger.warning(
            "ollama_embedding_connection_error model=%s error_type=%s retryable=true",
            model,
            type(exc).__name__,
        )
        raise EmbeddingRetryableError(
            "Cannot connect to Ollama. Ensure it is running and reachable at OLLAMA_BASE_URL."
        ) from exc
    except (AttributeError, IndexError, TypeError, ValueError) as exc:
        logger.error(
            "ollama_embedding_invalid_response model=%s error_type=%s",
            model,
            type(exc).__name__,
        )
        raise EmbeddingError(
            f"Ollama returned an invalid embedding; expected {EMBEDDING_DIMENSIONS} dimensions."
        ) from exc


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)
