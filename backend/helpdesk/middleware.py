"""Record security-relevant user actions without storing request contents."""

import json
import logging

from django.utils.deprecation import MiddlewareMixin

from accounts.models import AuditLog


logger = logging.getLogger(__name__)


class AuditLogMiddleware(MiddlewareMixin):
    """Audit successful logins, logouts, ticket status changes, and AI acceptance."""

    def process_request(self, request):
        user = getattr(request, "user", None)
        request.audit_user = user if user and user.is_authenticated else None

    def process_response(self, request, response):
        method = request.method
        path = request.path
        user = getattr(request, "audit_user", None)
        action = None
        details = {"status_code": response.status_code}

        if method == "POST" and path == "/api/auth/login/" and response.status_code == 200:
            action = "Login"
            user = getattr(request, "user", None)
        elif method == "POST" and path == "/api/auth/logout/" and response.status_code == 200:
            action = "Logout"
        elif (
            method in {"PATCH", "PUT"}
            and "/api/tickets/" in path
            and "/messages/" not in path
            and response.status_code == 200
        ):
            try:
                body = json.loads(request.body or b"{}")
            except (json.JSONDecodeError, UnicodeDecodeError):
                body = {}
            if isinstance(body, dict) and "status" in body:
                action = "Ticket Status Change"
                details.update({"path": path, "status": str(body["status"])[:32]})
        elif (
            method == "POST"
            and path.endswith("/accept-suggestion/")
            and response.status_code == 200
        ):
            action = "AI Suggestion Accepted"
            details["path"] = path

        if action and user and user.is_authenticated:
            try:
                AuditLog.objects.create(
                    user=user,
                    action=action,
                    ip_address=request.META.get("REMOTE_ADDR"),
                    details=details,
                )
            except Exception:
                # Logging failure must not turn a successful user operation into a 500.
                logger.exception("Unable to persist audit event %s", action)

        return response
