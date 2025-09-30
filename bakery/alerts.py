from __future__ import annotations

import json
import os
from typing import List, Optional

import requests
from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Sum

from .models import Product, StockLedger


def current_stock(product_id: int, outlet_id: Optional[int] = None) -> float:
    qs = StockLedger.objects.filter(item_type=StockLedger.PRODUCT, item_id=product_id)
    if outlet_id:
        qs = qs.filter(outlet_id=outlet_id)
    agg = qs.aggregate(qty_in=Sum("qty_in"), qty_out=Sum("qty_out"))
    qty_in = agg.get("qty_in") or 0
    qty_out = agg.get("qty_out") or 0
    return float(qty_in - qty_out)


def check_low_stock() -> List[dict]:
    items: List[dict] = []
    products = Product.objects.filter(reorder_threshold__gt=0)
    for product in products:
        stock = current_stock(product.id)
        if stock <= product.reorder_threshold:
            items.append(
                {
                    "product_id": product.id,
                    "name": product.name,
                    "stock": stock,
                    "threshold": product.reorder_threshold,
                }
            )
    return items


def send_email_low_stock(items: List[dict], recipients: Optional[List[str]] = None) -> None:
    if not items:
        return
    recipients = [email for email in (recipients or []) if email]
    if not recipients:
        return

    subject = "Low stock alert"
    lines = ["The following products are below their reorder threshold:
"]
    for item in items:
        lines.append(
            f"- {item['name']} (ID {item['product_id']}): stock {item['stock']} <= threshold {item['threshold']}"
        )
    message = "
".join(lines)

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com")
    send_mail(subject, message, from_email, recipients, fail_silently=True)


def send_webhook_low_stock(items: List[dict], url: Optional[str]) -> None:
    if not items or not url:
        return
    try:
        requests.post(url, data=json.dumps({"items": items}), headers={"Content-Type": "application/json"}, timeout=10)
    except requests.RequestException:
        pass


def run_low_stock_alerts():
    items = check_low_stock()
    if not items:
        return items

    emails_env = os.environ.get("STOCK_ALERT_EMAILS", "")
    emails = [email.strip() for email in emails_env.split(",") if email.strip()]
    send_email_low_stock(items, emails)

    webhook = os.environ.get("STOCK_ALERT_WEBHOOK")
    send_webhook_low_stock(items, webhook)
    return items
