# bakery/serializers.py
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from rest_framework import serializers
from .models import (
    Outlet,
    Product,
    Batch,
    Sale,
    SaleItem,
    StockLedger,
    Employee,
    Attendance,
    PayrollPeriod,
    PayrollEntry,
)
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


class EmployeeSerializer(serializers.ModelSerializer):
    outlet_name = serializers.CharField(source="outlet.name", read_only=True)

    class Meta:
        model = Employee
        fields = [
            "id",
            "first_name",
            "last_name",
            "phone",
            "is_active",
            "outlet",
            "outlet_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class AttendanceSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()
    outlet_id = serializers.IntegerField(source="employee.outlet_id", read_only=True)
    outlet_name = serializers.CharField(source="employee.outlet.name", read_only=True)

    class Meta:
        model = Attendance
        fields = [
            "id",
            "employee",
            "employee_name",
            "outlet_id",
            "outlet_name",
            "date",
            "check_in",
            "check_out",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_employee_name(self, obj):
        return str(obj.employee) if obj.employee_id else ""


class PayrollPeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollPeriod
        fields = [
            "id",
            "name",
            "start_date",
            "end_date",
            "is_closed",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class PayrollEntrySerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()
    outlet_id = serializers.IntegerField(source="employee.outlet_id", read_only=True)
    outlet_name = serializers.CharField(source="employee.outlet.name", read_only=True)

    class Meta:
        model = PayrollEntry
        fields = [
            "id",
            "period",
            "employee",
            "employee_name",
            "outlet_id",
            "outlet_name",
            "days_present",
            "gross_pay",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["days_present", "gross_pay", "created_at", "updated_at"]

    def get_employee_name(self, obj):
        return str(obj.employee) if obj.employee_id else ""


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
        fields = [
            "id",
            "product",
            "product_name",
            "qty",
            "unit_price",
            "tax_pct",
        ]


class SaleSerializer(serializers.ModelSerializer):
    items = SaleItemReadSerializer(many=True, read_only=True)
    write_items = SaleItemWriteSerializer(many=True, write_only=True, required=True)
    outlet_detail = OutletSerializer(source="outlet", read_only=True)

    class Meta:
        model = Sale
        fields = [
            "id",
            "outlet",
            "outlet_detail",
            "billed_at",
            "subtotal",
            "tax",
            "discount",
            "total",
            "payment_mode",
            "items",
            "write_items",
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
    actor_email = serializers.EmailField(source="actor.email", read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "actor",
            "actor_email",
            "action",
            "table",
            "row_id",
            "before",
            "after",
            "ip",
            "ua",
            "created_at",
        ]


class StockAlertRow(serializers.Serializer):
    product_id = serializers.IntegerField()
    product_name = serializers.CharField()
    outlet_id = serializers.IntegerField(allow_null=True)
    outlet_name = serializers.CharField(allow_blank=True)
    qty_on_hand = serializers.FloatField()
    threshold = serializers.FloatField()
