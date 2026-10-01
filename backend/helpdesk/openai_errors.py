def is_quota_exhausted(error: Exception) -> bool:
    """Identify OpenAI's non-retryable insufficient-credit rate-limit response."""
    body = getattr(error, "body", None)
    if not isinstance(body, dict):
        return False
    details = body.get("error", body)
    if not isinstance(details, dict):
        return False
    return details.get("code") in {"insufficient_quota", "credit_balance_exhausted"} or (
        details.get("type") == "insufficient_quota"
    )
