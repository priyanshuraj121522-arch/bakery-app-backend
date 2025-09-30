# bakery/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    OutletViewSet,
    ProductViewSet,
    BatchViewSet,
    SaleViewSet,
    AuditLogViewSet,
    me,
    health,
)
from .report_views import owner_summary
from .import_views import import_products, import_sales

# Routers for CRUD endpoints
router = DefaultRouter()
router.register("outlets", OutletViewSet)
router.register("products", ProductViewSet)
router.register("batches", BatchViewSet)
router.register("sales", SaleViewSet, basename="sale")
router.register("audit", AuditLogViewSet, basename="auditlog")

# Explicit endpoints
urlpatterns = [
    path("", include(router.urls)),
    path("health/", health, name="health"),          # /api/health/
    path("me/", me, name="me"),                      # /api/me/
    path("reports/owner-summary/", owner_summary, name="owner-summary"),
    path("import/products/", import_products, name="import-products"),
    path("import/sales/", import_sales, name="import-sales"),
]
