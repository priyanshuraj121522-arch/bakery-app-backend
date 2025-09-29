# bakery/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    OutletViewSet,
    ProductViewSet,
    BatchViewSet,
    SaleViewSet,
    me,
    health,
)
from .report_views import owner_summary

# Routers for CRUD endpoints
router = DefaultRouter()
router.register("outlets", OutletViewSet)
router.register("products", ProductViewSet)
router.register("batches", BatchViewSet)
router.register("sales", SaleViewSet, basename="sale")

# Explicit endpoints
urlpatterns = [
    path("", include(router.urls)),
    path("health/", health, name="health"),          # /api/health/
    path("me/", me, name="me"),                      # /api/me/
    path("reports/owner-summary/", owner_summary, name="owner-summary"),
]