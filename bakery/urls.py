from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    OutletViewSet, ProductViewSet, BatchViewSet, SaleViewSet,
    health,  # or health_check if that’s the name you actually use
    me,
)
from .report_views import owner_summary

router = DefaultRouter()
router.register("outlets", OutletViewSet)
router.register("products", ProductViewSet")
router.register("batches", BatchViewSet)
router.register("sales", SaleViewSet, basename="sale")

urlpatterns = [
    path("", include(router.urls)),
    path("reports/owner-summary/", owner_summary, name="owner-summary"),
    path("health/", health, name="health"),  # /api/health/
    path("me/", me, name="me"),              # /api/me/
]