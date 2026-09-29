import json
from django.utils.deprecation import MiddlewareMixin
from accounts.models import AuditLog

class AuditLogMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request._body = request.body

    def process_response(self, request, response):
        if not hasattr(request, 'user') or not request.user.is_authenticated:
            return response

        path = request.path
        method = request.method
        ip_address = request.META.get('REMOTE_ADDR')

        # Logins
        if method == 'POST' and path.endswith('/api/accounts/login/'):
            if response.status_code == 200:
                AuditLog.objects.create(
                    user=request.user,
                    action='Login',
                    ip_address=ip_address,
                    details={'status_code': response.status_code}
                )

        # Logouts
        elif method == 'POST' and path.endswith('/api/accounts/logout/'):
            AuditLog.objects.create(
                user=request.user,
                action='Logout',
                ip_address=ip_address,
                details={'status_code': response.status_code}
            )

        # Ticket status changes
        elif method in ['PATCH', 'PUT'] and '/api/tickets/' in path and not '/messages' in path:
            try:
                body = json.loads(request._body)
                if 'status' in body:
                    AuditLog.objects.create(
                        user=request.user,
                        action='Ticket Status Change',
                        ip_address=ip_address,
                        details={'path': path, 'status': body['status']}
                    )
            except Exception:
                pass

        # AI suggestion acceptances
        elif method == 'POST' and '/accept-suggestion' in path:
            if response.status_code == 200:
                AuditLog.objects.create(
                    user=request.user,
                    action='AI Suggestion Accepted',
                    ip_address=ip_address,
                    details={'path': path}
                )

        return response
