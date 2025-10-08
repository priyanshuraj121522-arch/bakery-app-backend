# bakery/urls.py
from django.urls import path, include, re_path
from rest_framework.routers import DefaultRouter

from .auth_views import login_flexible, refresh_view
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
from .report_views import (
    owner_summary,
    cogs_report,
    gross_costs_summary,
    exec_summary,
    reports_sales_trend,
    reports_top_products,
    reports_top_outlets,
    reports_revenue_vs_cogs,
)
from .inventory_views import inventory_overview
from .import_views import (
    import_products,
    import_sales,
    ImportPresetViewSet,
    ImportJobViewSet,
    ImportStartView,
)
from .upload_views import upload_data, upload_status

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

urlpatterns = [
    path("", include(router.urls)),

    # Auth & health
    path("auth/login/", login_flexible, name="api-login"),
    path("auth/refresh/", refresh_view, name="api-auth-refresh"),
    path("health/", health, name="health"),
    path("health/db/", health_db, name="health-db"),

    # User info
    path("me/", me, name="me"),

    # Dashboard data
    path("reports/owner-summary/", owner_summary, name="owner-summary"),
    path("reports/exec-summary/", exec_summary, name="exec-summary"),
    path("reports/sales-trend/", reports_sales_trend, name="reports-sales-trend"),
    path("reports/top-products/", reports_top_products, name="reports-top-products"),
    path("reports/top-outlets/", reports_top_outlets, name="reports-top-outlets"),
    path("reports/revenue-vs-cogs/", reports_revenue_vs_cogs, name="reports-revenue-vs-cogs"),
    re_path(r"^api/reports/revenue-vs-cogs/?$", reports_revenue_vs_cogs, name="reports-revenue-vs-cogs"),

    # Financial & inventory
    path("reports/cogs/", cogs_report, name="cogs-report"),
    path("reports/gross-costs/", gross_costs_summary, name="gross-costs"),
    path("inventory/overview/", inventory_overview, name="inventory-overview"),

    # Import/Export
    path("import/products/", import_products, name="import-products"),
    path("import/sales/", import_sales, name="import-sales"),
    path("import/start/", ImportStartView.as_view(), name="import-start"),
    path("exports/sales", ExportSalesView.as_view(), name="export-sales"),
    path("exports/products", ExportProductsView.as_view(), name="export-products"),

    # Tools/Admin
    path("tools/stock-check/", stock_check_now, name="stock-check"),
    path("admin/summary/", admin_summary, name="dashboard-summary"),

    # Payroll
    path("payroll/calc/", PayrollCalculationView.as_view(), name="payroll-calc"),
    path("upload-data/", upload_data, name="upload-data"),
    path("upload-status/<int:pk>/", upload_status, name="upload-status"),
]
