# bakery/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import auth_views as bakery_auth_views
from .views import (
    OutletViewSet,
    ProductViewSet,
    BatchViewSet,
    SaleViewSet,
    me,
    health,
    health_db,
)
from .attendance_views import EmployeeViewSet, AttendanceViewSet
from .payroll_views import PayrollEntryViewSet, PayrollCalculationView, PayrollPeriodViewSet
from .admin_views import AuditLogViewSet, stock_check_now, admin_summary
from .exports import ExportSalesView, ExportProductsView
from .report_views import owner_summary, cogs_report, gross_costs_summary
from .import_views import (
    import_products,
    import_sales,
    ImportPresetViewSet,
    ImportJobViewSet,
    ImportStartView,
)

# Routers for CRUD endpoints
router = DefaultRouter()
router.register("outlets", OutletViewSet)
router.register("products", ProductViewSet)
router.register("batches", BatchViewSet)
router.register("sales", SaleViewSet, basename="sale")
router.register("audit/logs", AuditLogViewSet, basename="audit-log")
router.register("employees", EmployeeViewSet)
router.register("attendance", AttendanceViewSet)
router.register("payroll/periods", PayrollPeriodViewSet)
router.register("payroll/entries", PayrollEntryViewSet, basename="payroll-entry")
router.register("import/presets", ImportPresetViewSet, basename="import-preset")
router.register("import/jobs", ImportJobViewSet, basename="import-job")

# Explicit endpoints
urlpatterns = [
    path("", include(router.urls)),
    path("auth/login/", bakery_auth_views.login_view, name="api-auth-login"),
    path("auth/refresh/", bakery_auth_views.refresh_view, name="api-auth-refresh"),
    path("health/", health, name="health"),          # /api/health/
    path("health/db/", health_db, name="health-db"),
    path("me/", me, name="me"),                      # /api/me/
    path("reports/owner-summary/", owner_summary, name="owner-summary"),
    path("reports/cogs/", cogs_report, name="cogs-report"),
    path("reports/gross-costs/", gross_costs_summary, name="gross-costs"),
    path("import/products/", import_products, name="import-products"),
    path("import/sales/", import_sales, name="import-sales"),
    path("import/start/", ImportStartView.as_view(), name="import-start"),
    path("tools/stock-check/", stock_check_now, name="stock-check"),
    path("admin/summary/", admin_summary, name="dashboard-summary"),
    path("exports/sales", ExportSalesView.as_view(), name="export-sales"),
    path("exports/products", ExportProductsView.as_view(), name="export-products"),
    path("payroll/calc/", PayrollCalculationView.as_view(), name="payroll-calc"),
]
