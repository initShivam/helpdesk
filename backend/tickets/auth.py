from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import NotAuthenticated

class SessionAuthenticationWith401(SessionAuthentication):
    """SessionAuthentication that returns 401 for unauthenticated requests.
    Preserves CSRF protection for authenticated sessions.
    """
    def authenticate(self, request):
        # request.user is set by Django's AuthenticationMiddleware
        user = getattr(request._request, 'user', None)
        if not user or not user.is_authenticated:
            raise NotAuthenticated('Authentication credentials were not provided.')
        return super().authenticate(request)

    def authenticate_header(self, request):
        return 'Session'
