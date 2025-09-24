from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import OutletViewSet, ProductViewSet, BatchViewSet, SaleViewSet
from .report_views import owner_summary   # NEW

router = DefaultRouter()
router.register("outlets", OutletViewSet)
router.register("products", ProductViewSet)
router.register("batches", BatchViewSet)
router.register("sales", SaleViewSet)

urlpatterns = [
    path("", include(router.urls)),
    path("reports/owner-summary/", owner_summary, name="owner-summary"),  # NEW
]
