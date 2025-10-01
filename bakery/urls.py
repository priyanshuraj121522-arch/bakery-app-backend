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
from .attendance_views import EmployeeViewSet, AttendanceViewSet
from .admin_views import AuditLogViewSet, stock_check_now, admin_summary
from .exports import ExportSalesView, ExportProductsView
from .report_views import owner_summary
from .import_views import import_products, import_sales

# Routers for CRUD endpoints
router = DefaultRouter()
router.register("outlets", OutletViewSet)
router.register("products", ProductViewSet)
router.register("batches", BatchViewSet)
router.register("sales", SaleViewSet, basename="sale")
router.register("audit/logs", AuditLogViewSet, basename="audit-log")
router.register("employees", EmployeeViewSet)
router.register("attendance", AttendanceViewSet)

# Explicit endpoints
urlpatterns = [
    path("", include(router.urls)),
    path("health/", health, name="health"),          # /api/health/
    path("me/", me, name="me"),                      # /api/me/
    path("reports/owner-summary/", owner_summary, name="owner-summary"),
    path("import/products/", import_products, name="import-products"),
    path("import/sales/", import_sales, name="import-sales"),
    path("tools/stock-check/", stock_check_now, name="stock-check"),
    path("admin/summary/", admin_summary, name="dashboard-summary"),
    path("exports/sales", ExportSalesView.as_view(), name="export-sales"),
    path("exports/products", ExportProductsView.as_view(), name="export-products"),
]
