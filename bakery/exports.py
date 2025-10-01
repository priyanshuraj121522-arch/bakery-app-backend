from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timedelta
from typing import Iterable

from django.db.models import F, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from .models import Sale, SaleItem, Product

try:
    from openpyxl import Workbook
except ImportError:  # pragma: no cover
    Workbook = None  # type: ignore

log = logging.getLogger(__name__)

DATE_FORMATS = ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f")


def parse_date(value: str | None, default: datetime) -> datetime:
    if not value:
        return default
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.get_current_timezone())
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = timezone.make_aware(dt)
        return dt
    except ValueError:
        log.warning("Invalid date value '%s', using default", value)
        return default


def build_sales_queryset(date_from: datetime | None, date_to: datetime | None, outlet_id: int | None):
    qs = Sale.objects.select_related("outlet").prefetch_related("items__product")
    if date_from:
        qs = qs.filter(billed_at__gte=date_from)
    if date_to:
        qs = qs.filter(billed_at__lte=date_to)
    if outlet_id:
        qs = qs.filter(outlet_id=outlet_id)
    return qs.order_by("billed_at")


def sale_items_summary(items: Iterable[SaleItem]) -> str:
    parts: list[str] = []
    for item in items:
        sku = getattr(item.product, "sku", "") or "SKU"
        parts.append(
            f"{sku} x {item.qty} @ {item.unit_price} ({item.tax_pct}%)"
        )
    return "; ".join(parts)


def sales_to_csv(qs: Iterable[Sale]) -> HttpResponse:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "id",
        "outlet",
        "billed_at",
        "payment_mode",
        "subtotal",
        "tax",
        "discount",
        "total",
        "items",
    ])
    for sale in qs:
        items_summary = sale_items_summary(sale.items.all())
        billed = getattr(sale, "billed_at", None)
        writer.writerow([
            sale.id,
            getattr(sale.outlet, "name", ""),
            billed.isoformat() if billed else "",
            sale.payment_mode,
            sale.subtotal,
            sale.tax,
            sale.discount,
            sale.total,
            items_summary,
        ])
    resp = HttpResponse(buffer.getvalue(), content_type="text/csv")
    resp.charset = "utf-8"
    return resp


def sales_to_xlsx(qs: Iterable[Sale]) -> HttpResponse:
    if Workbook is None:
        raise RuntimeError("openpyxl is required for XLSX exports")
    wb = Workbook()
    ws = wb.active
    ws.title = "Sales"
    ws.append([
        "id",
        "outlet",
        "billed_at",
        "payment_mode",
        "subtotal",
        "tax",
        "discount",
        "total",
        "items",
    ])
    for sale in qs:
        items_summary = sale_items_summary(sale.items.all())
        billed = getattr(sale, "billed_at", None)
        ws.append([
            sale.id,
            getattr(sale.outlet, "name", ""),
            billed.isoformat() if billed else "",
            sale.payment_mode,
            float(sale.subtotal or 0),
            float(sale.tax or 0),
            float(sale.discount or 0),
            float(sale.total or 0),
            items_summary,
        ])
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    resp = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    return resp


def products_to_csv(qs: Iterable[Product]) -> HttpResponse:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "id",
        "sku",
        "name",
        "mrp",
        "tax_pct",
        "current_stock",
        "reorder_threshold",
        "created_at",
        "updated_at",
    ])
    for product in qs:
        writer.writerow([
            product.id,
            product.sku,
            product.name,
            product.mrp,
            product.tax_pct,
            "",
            getattr(product, "reorder_threshold", ""),
            getattr(product, "created_at", ""),
            getattr(product, "updated_at", ""),
        ])
    resp = HttpResponse(buffer.getvalue(), content_type="text/csv")
    resp.charset = "utf-8"
    return resp


def products_to_xlsx(qs: Iterable[Product]) -> HttpResponse:
    if Workbook is None:
        raise RuntimeError("openpyxl is required for XLSX exports")
    wb = Workbook()
    ws = wb.active
    ws.title = "Products"
    ws.append([
        "id",
        "sku",
        "name",
        "mrp",
        "tax_pct",
        "current_stock",
        "reorder_threshold",
        "created_at",
        "updated_at",
    ])
    for product in qs:
        ws.append([
            product.id,
            product.sku,
            product.name,
            float(product.mrp or 0),
            float(product.tax_pct or 0),
            "",
            getattr(product, "reorder_threshold", ""),
            getattr(product, "created_at", ""),
            getattr(product, "updated_at", ""),
        ])
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    resp = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    return resp


class ExportSalesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        params = request.query_params
        now = timezone.now()
        default_start = now - timedelta(days=30)
        date_from = parse_date(params.get("date_from"), default_start)
        date_to = parse_date(params.get("date_to"), now)
        outlet = params.get("outlet")
        outlet_id = None
        if outlet:
            try:
                outlet_id = int(outlet)
            except (TypeError, ValueError):
                outlet_id = None
        format_param = params.get("format", "csv").lower()
        queryset = list(build_sales_queryset(date_from, date_to, outlet_id))

        filename = f"sales_{date_from.date()}_{date_to.date()}.{format_param}"
        try:
            if format_param == "xlsx":
                response = sales_to_xlsx(queryset)
            else:
                response = sales_to_csv(queryset)
            response["Content-Disposition"] = f"attachment; filename={filename}"
            return response
        except Exception:
            log.exception("Failed generating sales export")
            return HttpResponse(status=500)


class ExportProductsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        format_param = request.query_params.get("format", "csv").lower()
        queryset = Product.objects.all().order_by("name")
        try:
            if format_param == "xlsx":
                response = products_to_xlsx(queryset)
            else:
                response = products_to_csv(queryset)
            response["Content-Disposition"] = f"attachment; filename=products.{format_param}"
            return response
        except Exception:
            log.exception("Failed generating products export")
            return HttpResponse(status=500)
