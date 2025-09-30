from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime
import json

from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError

from .models import Product, Outlet
from .serializers import SaleSerializer
from .import_utils import load_tabular


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _as_decimal(value, default="0") -> Decimal:
    if value is None or value == "":
        value = default
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise ValidationError(f"Invalid decimal value: {value}")


def _parse_rows(request):
    try:
        rows = load_tabular(request)
    except Exception as exc:  # pylint: disable=broad-except
        raise ValidationError(str(exc))
    if not isinstance(rows, list):
        raise ValidationError("Unable to parse sheet")
    return rows


def _parse_dry_run(request) -> bool:
    candidate = request.data.get("dry_run") or request.query_params.get("dry_run")
    return _as_bool(candidate)


def _stringify(message: object) -> str:
    if isinstance(message, str):
        return message
    try:
        return json.dumps(message, default=str)
    except TypeError:
        return str(message)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def import_products(request):
    rows = _parse_rows(request)
    dry_run = _parse_dry_run(request)

    created = 0
    updated = 0
    errors = []

    sample = rows[:3]

    with transaction.atomic():
    for idx, row in enumerate(rows, start=1):
        sku = str(row.get("sku", "")).strip()
        name = str(row.get("name", "")).strip()
        if not sku:
            errors.append({"row": idx, "message": "Missing SKU"})
            continue
        if not name:
            errors.append({"row": idx, "message": "Missing name"})
            continue
        if row.get("mrp") in (None, ""):
            errors.append({"row": idx, "message": "Missing mrp"})
            continue
        try:
            mrp = _as_decimal(row.get("mrp"))
            tax_pct = _as_decimal(row.get("tax_pct"), default="0")
        except ValidationError as exc:
            detail = getattr(exc, "detail", str(exc))
            errors.append({"row": idx, "message": _stringify(detail)})
            continue

        mrp = mrp.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        tax_pct = tax_pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        active_value = row.get("active", True)
        active = True
        if active_value not in (None, ""):
            active = _as_bool(active_value)

        product, created_flag = Product.objects.get_or_create(sku=sku, defaults={
            "name": name,
            "mrp": mrp,
            "tax_pct": tax_pct,
            "active": active,
        })
        if created_flag:
            created += 1
            continue

        dirty = False
        if product.name != name:
            product.name = name
            dirty = True
            if product.mrp != mrp:
                product.mrp = mrp
                dirty = True
            if product.tax_pct != tax_pct:
            product.tax_pct = tax_pct
            dirty = True
        if product.active != active:
            product.active = active
            dirty = True

        if dirty:
            product.save()
            updated += 1

        if dry_run:
            transaction.set_rollback(True)

    return Response({
        "ok": True,
        "dry_run": dry_run,
        "created": created,
        "updated": updated,
        "errors": errors,
        "sample": sample,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def import_sales(request):
    rows = _parse_rows(request)
    dry_run = _parse_dry_run(request)

    created = 0
    errors = []
    sample = rows[:3]

    with transaction.atomic():
        for idx, row in enumerate(rows, start=1):
            outlet_raw = row.get("outlet")
            product_sku = str(row.get("product_sku", "")).strip()
            if not outlet_raw:
                errors.append({"row": idx, "message": "Missing outlet"})
                continue
            if not product_sku:
                errors.append({"row": idx, "message": "Missing product_sku"})
                continue

            outlet = None
            try:
                outlet = Outlet.objects.filter(id=int(outlet_raw)).first()
            except (TypeError, ValueError):
                outlet = None
            if outlet is None:
                outlet = Outlet.objects.filter(name=str(outlet_raw).strip()).first()
            if outlet is None:
                errors.append({"row": idx, "message": f"Outlet not found: {outlet_raw}"})
                continue

            try:
                product = Product.objects.get(sku=product_sku)
            except Product.DoesNotExist:
                errors.append({"row": idx, "message": f"Product not found for SKU {product_sku}"})
                continue

            try:
                qty = Decimal(str(row.get("qty")))
                if qty <= 0:
                    raise InvalidOperation
            except (InvalidOperation, TypeError):
                errors.append({"row": idx, "message": "Invalid qty"})
                continue

            unit_price = row.get("unit_price")
            try:
                if unit_price in (None, ""):
                    unit_price = product.mrp
                unit_price = Decimal(str(unit_price))
                unit_price = unit_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            except (InvalidOperation, TypeError):
                errors.append({"row": idx, "message": "Invalid unit_price"})
                continue

            tax_pct = row.get("tax_pct")
            try:
                if tax_pct in (None, ""):
                    tax_pct = product.tax_pct
                tax_pct = Decimal(str(tax_pct))
                tax_pct = tax_pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            except (InvalidOperation, TypeError):
                errors.append({"row": idx, "message": "Invalid tax_pct"})
                continue

            date_str = row.get("date")
            billed_date = timezone.localdate()
            if date_str:
                try:
                    billed_date = datetime.strptime(str(date_str), "%Y-%m-%d").date()
                except ValueError:
                    errors.append({"row": idx, "message": "Invalid date (expected YYYY-MM-DD)"})
                    continue

            payment_mode = (row.get("payment_mode") or "UPI").strip()

            payload = {
                "outlet": outlet.id,
                "payment_mode": payment_mode,
                "discount": "0",
                "write_items": [
                    {
                        "product": product.id,
                        "qty": float(qty),
                        "unit_price": str(unit_price),
                        "tax_pct": str(tax_pct),
                    }
                ],
            }

            serializer = SaleSerializer(data=payload)
            if not serializer.is_valid():
                errors.append({"row": idx, "message": _stringify(serializer.errors)})
                continue

            try:
                sale = serializer.save()
            except ValidationError as exc:
                detail = getattr(exc, "detail", str(exc))
                errors.append({"row": idx, "message": _stringify(detail)})
                continue
            if date_str:
                naive_dt = datetime.combine(billed_date, datetime.min.time())
                aware_dt = timezone.make_aware(naive_dt) if timezone.is_naive(naive_dt) else naive_dt
                sale.billed_at = aware_dt
                sale.save(update_fields=["billed_at"])

            created += 1

        if dry_run:
            transaction.set_rollback(True)

    return Response({
        "ok": True,
        "dry_run": dry_run,
        "created": created,
        "updated": 0,
        "errors": errors,
        "sample": sample,
    })
