# core/urls.py
from django.contrib import admin
from django.urls import path, include
from .auth_views import ThrottledTokenObtainPairView, ThrottledTokenRefreshView

urlpatterns = [
    path("admin/", admin.site.urls),

    # JWT
    path("api/auth/token/", ThrottledTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/refresh/", ThrottledTokenRefreshView.as_view(), name="token_refresh"),

    # App endpoints (this includes /api/me/ and /api/health/)
    path("api/", include("bakery.urls")),
]