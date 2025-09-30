# bakery/serializers.py
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from rest_framework import serializers
from .models import Outlet, Product, Batch, Sale, SaleItem, StockLedger
from .models_audit import AuditLog

def money(x) -> Decimal:
    return (Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

class OutletSerializer(serializers.ModelSerializer):
    class Meta:
        model = Outlet
        fields = "__all__"

class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = "__all__"

class BatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Batch
        fields = "__all__"

class SaleItemWriteSerializer(serializers.Serializer):
    """Write-only serializer for nested line items when creating a Sale."""
    product = serializers.IntegerField()         # product id
    qty = serializers.FloatField(min_value=0.01)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    tax_pct = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)

class SaleItemReadSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    class Meta:
        model = SaleItem
        fields = ["id", "product", "product_name", "qty", "unit_price", "tax_pct"]

class SaleSerializer(serializers.ModelSerializer):
    # read
    items = SaleItemReadSerializer(many=True, read_only=True)
    # write
    write_items = SaleItemWriteSerializer(many=True, write_only=True, required=True)

    class Meta:
        model = Sale
        fields = [
            "id", "outlet", "billed_at", "subtotal", "tax", "discount", "total",
            "payment_mode", "items", "write_items"
        ]
        read_only_fields = ["subtotal", "tax", "total", "billed_at"]

    def validate(self, attrs):
        # Basic check: at least one line
        lines = attrs.get("write_items") or []
        if not lines:
            raise serializers.ValidationError("At least one line item is required.")
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        """
        Create a Sale with nested SaleItems.
        Totals are recomputed on the server for robustness.
        Also writes StockLedger 'sale' entries (qty_out).
        """
        lines = validated_data.pop("write_items")
        outlet = validated_data["outlet"]

        subtotal = Decimal("0.00")
        total_tax = Decimal("0.00")

        sale = Sale.objects.create(
            outlet=outlet,
            subtotal=Decimal("0.00"),
            tax=Decimal("0.00"),
            discount=validated_data.get("discount") or Decimal("0.00"),
            total=Decimal("0.00"),
            payment_mode=validated_data.get("payment_mode") or "UPI",
        )

        for line in lines:
            product = Product.objects.get(pk=line["product"])

            # default unit_price from product MRP if not provided
            unit_price = money(line.get("unit_price", product.mrp))
            tax_pct = Decimal(line.get("tax_pct", product.tax_pct))

            qty = Decimal(str(line["qty"]))
            line_subtotal = unit_price * qty
            line_tax = (line_subtotal * tax_pct / Decimal("100")).quantize(Decimal("0.01"))

            # persist item
            item = SaleItem.objects.create(
                sale=sale,
                product=product,
                qty=float(qty),
                unit_price=unit_price,
                tax_pct=tax_pct
            )

            # stock ledger (finished goods going OUT from outlet)
            StockLedger.objects.create(
                item_type=StockLedger.PRODUCT,
                item_id=product.id,
                outlet=outlet,
                batch=None,  # enhancement later: pick FEFO batch & set batch here
                qty_in=0,
                qty_out=float(qty),
                reason="sale",
                ref_table="sale_item",
                ref_id=item.id,
            )

            subtotal += line_subtotal
            total_tax += line_tax

        discount = money(validated_data.get("discount", 0))
        computed_total = money(subtotal + total_tax - discount)

        sale.subtotal = money(subtotal)
        sale.tax = money(total_tax)
        sale.total = computed_total
        sale.save()

        return sale


class AuditLogSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "actor_username",
            "action",
            "table",
            "row_id",
            "before",
            "after",
            "ip",
            "ua",
            "created_at",
        ]

