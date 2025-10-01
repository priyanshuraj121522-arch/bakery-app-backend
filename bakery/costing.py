"""COGS computation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Sequence

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import PurchaseBatch, Sale, CogsEntry


@dataclass
class BatchAllocation:
    batch: PurchaseBatch
    qty: float


def _allocate_fifo(batches: Sequence[PurchaseBatch], qty_needed: float) -> List[BatchAllocation]:
    remaining = qty_needed
    allocations: List[BatchAllocation] = []
    for batch in batches:
        if remaining <= 0:
            break
        available = max(batch.qty_remaining, 0)
        if available <= 0:
            continue
        use_qty = float(min(available, remaining))
        if use_qty <= 0:
            continue
        allocations.append(BatchAllocation(batch=batch, qty=use_qty))
        remaining -= use_qty
    if remaining > 1e-6:
        raise ValueError("Insufficient inventory to compute COGS")
    return allocations


def pick_batches_fifo(product_id: int, outlet_id: int, qty: float) -> List[BatchAllocation]:
    batches = list(
        PurchaseBatch.objects.select_for_update()
        .filter(product_id=product_id, outlet_id=outlet_id)
        .order_by("received_at", "id")
    )
    return _allocate_fifo(batches, qty)


def pick_batches_fefo(product_id: int, outlet_id: int, qty: float) -> List[BatchAllocation]:
    batches = list(
        PurchaseBatch.objects.select_for_update()
        .filter(product_id=product_id, outlet_id=outlet_id)
        .order_by(F("expiry").asc(nulls_last=True), "received_at", "id")
    )
    return _allocate_fifo(batches, qty)


def compute_cogs_for_sale(sale: Sale, method: str = CogsEntry.FIFO) -> None:
    items = list(sale.items.select_related("product"))
    if not items:
        return

    with transaction.atomic():
        for item in items:
            if CogsEntry.objects.filter(sale_item=item).exists():
                continue

            product = item.product
            qty = float(item.qty)
            outlet_id = sale.outlet_id

            if method == CogsEntry.FEFO:
                allocations = pick_batches_fefo(product.id, outlet_id, qty)
            else:
                allocations = pick_batches_fifo(product.id, outlet_id, qty)

            total_cost = Decimal("0")
            weighted_qty = Decimal("0")
            for allocation in allocations:
                batch = allocation.batch
                use_qty = Decimal(str(allocation.qty))
                total_cost += use_qty * batch.unit_cost
                weighted_qty += use_qty

                batch.qty_remaining = float(Decimal(str(batch.qty_remaining)) - use_qty)
                if batch.qty_remaining < 0:
                    batch.qty_remaining = 0
                batch.save(update_fields=["qty_remaining", "updated_at"])

            unit_cost = (total_cost / weighted_qty) if weighted_qty else Decimal("0")

            CogsEntry.objects.create(
                sale_item=item,
                product=product,
                outlet_id=outlet_id,
                qty=qty,
                unit_cost=unit_cost.quantize(Decimal("0.01")),
                total_cost=total_cost.quantize(Decimal("0.01")),
                method=method,
                computed_at=timezone.now(),
            )
