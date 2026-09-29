import hashlib
import json
import math
from urllib import error, request

from django.conf import settings


class EmbeddingError(Exception):
    """Raised when an embedding provider cannot return a vector."""


def _local_embedding(text: str, dimensions: int = 768) -> list[float]:
    """Stable offline fallback used by tests and development without an API key."""
    vector = [0.0] * dimensions
    for token in text.lower().split():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        vector[index] += 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [round(value / norm, 8) for value in vector]


from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(EmbeddingError)
)
def embed_text(text: str) -> tuple[list[float], str]:
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    model = getattr(settings, "GEMINI_EMBEDDING_MODEL", "text-embedding-004")
    if not api_key:
        return _local_embedding(text), "local-hash-fallback"

    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent"
        f"?key={api_key}"
    )
    payload = json.dumps({"content": {"parts": [{"text": text}]}}).encode("utf-8")
    req = request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=getattr(settings, "AI_SUGGESTION_TIMEOUT", 30)) as response:
            data = json.loads(response.read().decode("utf-8"))
        values = data["embedding"]["values"]
        if not values:
            raise ValueError("empty embedding")
        return [float(value) for value in values], model
    except error.HTTPError as exc:
        if exc.code == 429:
            raise EmbeddingError("Rate limit exceeded.") from exc
        raise EmbeddingError("Embedding provider failed.") from exc
    except (error.URLError, TimeoutError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise EmbeddingError("Embedding provider failed.") from exc


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)
