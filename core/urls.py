# core/urls.py
from django.contrib import admin
from django.urls import path, include

from .auth_views import ThrottledTokenObtainPairView
from bakery.auth_views import refresh_view

urlpatterns = [
    path("admin/", admin.site.urls),

    # JWT
    path("api/auth/token/", ThrottledTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/refresh/", refresh_view, name="token_refresh"),

    # App endpoints (this includes /api/me/ and /api/health/)
    path("api/", include("bakery.urls")),
]
