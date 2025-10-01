from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime
import json

from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .import_utils import load_tabular, _normalize_header
from .models import Product, Outlet, ImportPreset, ImportJob
from .serializers import (
    SaleSerializer,
    ImportPresetSerializer,
    ImportJobSerializer,
)


# ---- helpers ---------------------------------------------------------------

def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _as_decimal(value, default="0") -> Decimal:
    if value in (None, ""):
        value = default
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise ValidationError(f"Invalid decimal value: {value}")


def _parse_rows(request):
    try:
        rows = load_tabular(request)
    except Exception as exc:  # broad catch, surface message to caller
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


def _prepare_mapping(raw_mapping):
    if not raw_mapping:
        return {}
    if isinstance(raw_mapping, str):
        try:
            raw_mapping = json.loads(raw_mapping)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Invalid mapping JSON: {exc}")
    if not isinstance(raw_mapping, dict):
        raise ValidationError("mapping must be an object")
    normalized = {}
    for key, value in raw_mapping.items():
        if value in (None, ""):
            continue
        normalized[key] = _normalize_header(str(value))
    return normalized


def _apply_mapping(rows, mapping):
    if not mapping:
        return rows
    remapped = []
    for row in rows:
        base = dict(row)
        for target, source_key in mapping.items():
            if source_key in row:
                base[target] = row[source_key]
        remapped.append(base)
    return remapped


def _run_product_import(rows, dry_run=False):
    created = 0
    updated = 0
    errors: list[dict] = []
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
            active = _as_bool(active_value) if active_value not in (None, "") else True

            product, created_flag = Product.objects.get_or_create(
                sku=sku,
                defaults={
                    "name": name,
                    "mrp": mrp,
                    "tax_pct": tax_pct,
                    "active": active,
                },
            )

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

    return {
        "ok": True,
        "dry_run": dry_run,
        "created": created,
        "updated": updated,
        "errors": errors,
        "sample": sample,
    }


def _run_sales_import(rows, dry_run=False):
    created = 0
    errors: list[dict] = []
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

            unit_price_value = row.get("unit_price")
            try:
                if unit_price_value in (None, ""):
                    unit_price_value = product.mrp
                unit_price = Decimal(str(unit_price_value)).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            except (InvalidOperation, TypeError):
                errors.append({"row": idx, "message": "Invalid unit_price"})
                continue

            tax_pct_value = row.get("tax_pct")
            try:
                if tax_pct_value in (None, ""):
                    tax_pct_value = product.tax_pct
                tax_pct = Decimal(str(tax_pct_value)).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
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
                aware_dt = timezone.make_aware(datetime.combine(billed_date, datetime.min.time()))
                sale.billed_at = aware_dt
                sale.save(update_fields=["billed_at"])

            created += 1

        if dry_run:
            transaction.set_rollback(True)

    return {
        "ok": True,
        "dry_run": dry_run,
        "created": created,
        "updated": 0,
        "errors": errors,
        "sample": sample,
    }


# ---- import products -------------------------------------------------------

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def import_products(request):
    rows = _parse_rows(request)
    dry_run = _parse_dry_run(request)
    result = _run_product_import(rows, dry_run=dry_run)
    return Response(result)


# ---- import sales ----------------------------------------------------------

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def import_sales(request):
    rows = _parse_rows(request)
    dry_run = _parse_dry_run(request)
    result = _run_sales_import(rows, dry_run=dry_run)
    return Response(result, status=status.HTTP_200_OK)


class ImportPresetViewSet(viewsets.ModelViewSet):
    """CRUD endpoints for saved import presets."""

    queryset = ImportPreset.objects.select_related("outlet", "created_by").all()
    serializer_class = ImportPresetSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return super().get_queryset()

    def perform_create(self, serializer):
        creator = self.request.user if self.request.user.is_authenticated else None
        serializer.save(created_by=creator)


class ImportJobViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only access to import job history."""

    queryset = ImportJob.objects.select_related("preset", "preset__outlet").all()
    serializer_class = ImportJobSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return super().get_queryset()


class ImportStartView(APIView):
    """Trigger a synchronous import run and capture the job outcome."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        kind = request.data.get("kind")
        valid_kinds = {choice[0] for choice in ImportPreset.KIND_CHOICES}
        if kind not in valid_kinds:
            return Response({"detail": "Invalid kind."}, status=status.HTTP_400_BAD_REQUEST)

        dry_run = _parse_dry_run(request)

        preset = None
        preset_id = request.data.get("preset_id") or request.data.get("preset")
        if preset_id:
            try:
                preset = ImportPreset.objects.get(id=preset_id)
            except ImportPreset.DoesNotExist:
                return Response({"detail": "Preset not found."}, status=status.HTTP_404_NOT_FOUND)
            if preset.kind != kind:
                return Response({"detail": "Preset kind mismatch."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            request_mapping = _prepare_mapping(request.data.get("mapping"))
        except ValidationError as exc:
            detail = getattr(exc, "detail", str(exc))
            return Response({"detail": _stringify(detail)}, status=status.HTTP_400_BAD_REQUEST)

        preset_mapping = {}
        if preset and preset.mapping:
            try:
                preset_mapping = _prepare_mapping(preset.mapping)
            except ValidationError:
                preset_mapping = {}

        mapping = {**preset_mapping, **request_mapping}

        file_name = request.data.get("file_name")
        if not file_name and request.FILES.get("file"):
            file_name = request.FILES["file"].name
        if not file_name:
            file_name = request.data.get("sheet_url") or request.query_params.get("sheet_url") or "import"

        job = ImportJob.objects.create(
            kind=kind,
            preset=preset,
            file_name=file_name,
            status=ImportJob.STATUS_QUEUED,
        )

        job.status = ImportJob.STATUS_RUNNING
        job.save(update_fields=["status"])

        try:
            rows = load_tabular(request)
        except ValidationError as exc:
            detail = getattr(exc, "detail", str(exc))
            job.status = ImportJob.STATUS_ERROR
            job.errors = [{"row": None, "message": _stringify(detail)}]
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "errors", "finished_at"])
            serializer = ImportJobSerializer(job)
            return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)

        mapped_rows = _apply_mapping(rows, mapping)
        result = {}
        try:
            if kind == ImportPreset.KIND_PRODUCTS:
                result = _run_product_import(mapped_rows, dry_run=dry_run)
            else:
                result = _run_sales_import(mapped_rows, dry_run=dry_run)
        except ValidationError as exc:
            detail = getattr(exc, "detail", str(exc))
            job.status = ImportJob.STATUS_ERROR
            job.errors = [{"row": None, "message": _stringify(detail)}]
            job.total_rows = len(rows)
            job.processed_rows = 0
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "errors", "total_rows", "processed_rows", "finished_at"])
            serializer = ImportJobSerializer(job)
            return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:  # pragma: no cover - defensive
            job.status = ImportJob.STATUS_ERROR
            job.errors = [{"row": None, "message": str(exc)}]
            job.total_rows = len(rows)
            job.processed_rows = 0
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "errors", "total_rows", "processed_rows", "finished_at"])
            serializer = ImportJobSerializer(job)
            return Response(serializer.data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        processed_rows = result.get("created", 0) + result.get("updated", 0)
        job.status = ImportJob.STATUS_DONE
        job.errors = result.get("errors", [])
        job.total_rows = len(rows)
        job.processed_rows = processed_rows
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "errors", "total_rows", "processed_rows", "finished_at"])

        serializer = ImportJobSerializer(job)
        return Response(serializer.data, status=status.HTTP_200_OK)
