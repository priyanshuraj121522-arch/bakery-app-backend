# core/urls.py
from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    # Django admin
    path("admin/", admin.site.urls),

    # JWT authentication (SimpleJWT)
    path("api/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

    # App API (this exposes /api/me/ and /api/health/ etc.)
    path("api/", include("bakery.urls")),
]