from django.urls import path
from .views import CsrfTokenView, LoginView, LogoutView, MeView, TokenLoginView

urlpatterns = [
    path('csrf/', CsrfTokenView.as_view(), name='csrf'),
    path('login/', LoginView.as_view(), name='login'),
    path('token-login/', TokenLoginView.as_view(), name='token-login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('me/', MeView.as_view(), name='me'),
]
