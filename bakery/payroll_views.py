"""Payroll management API endpoints."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Attendance, Employee, PayrollEntry, PayrollPeriod
from .serializers import PayrollEntrySerializer, PayrollPeriodSerializer

TWOPLACES = Decimal("0.01")


class PayrollPeriodViewSet(viewsets.ModelViewSet):
    """CRUD endpoints for managing payroll periods."""

    queryset = PayrollPeriod.objects.all()
    serializer_class = PayrollPeriodSerializer
    permission_classes = [IsAuthenticated]


class PayrollEntryViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only access to payroll entries."""

    queryset = PayrollEntry.objects.select_related("period", "employee", "employee__outlet").all()
    serializer_class = PayrollEntrySerializer
    permission_classes = [IsAuthenticated]


class PayrollCalculationView(APIView):
    """Generate payroll entries by rolling up attendance for a period."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        period_id = request.data.get("period_id")
        daily_rate_raw = request.data.get("daily_rate")
        outlet_id = request.data.get("outlet_id")

        if not period_id or daily_rate_raw is None:
            return Response(
                {"detail": "period_id and daily_rate are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            daily_rate = Decimal(str(daily_rate_raw)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        except (InvalidOperation, TypeError, ValueError):
            return Response(
                {"detail": "daily_rate must be a valid decimal string."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if daily_rate < 0:
            return Response(
                {"detail": "daily_rate cannot be negative."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        period = get_object_or_404(PayrollPeriod, pk=period_id)

        employees_qs = Employee.objects.filter(is_active=True).select_related("outlet")
        if outlet_id:
            employees_qs = employees_qs.filter(outlet_id=outlet_id)

        employees = list(employees_qs)
        if not employees:
            return Response([], status=status.HTTP_200_OK)

        attendance_counts = (
            Attendance.objects.filter(
                employee__in=employees,
                date__gte=period.start_date,
                date__lte=period.end_date,
            )
            .values("employee_id")
            .annotate(days=Count("id"))
        )
        attendance_map = {row["employee_id"]: Decimal(row["days"]) for row in attendance_counts}

        updated_entries = []
        with transaction.atomic():
            for employee in employees:
                days_present = attendance_map.get(employee.id, Decimal("0"))
                days_present = days_present.quantize(TWOPLACES)
                gross_pay = (days_present * daily_rate).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

                entry, _ = PayrollEntry.objects.update_or_create(
                    period=period,
                    employee=employee,
                    defaults={
                        "days_present": days_present,
                        "gross_pay": gross_pay,
                    },
                )
                updated_entries.append(entry)

        serializer = PayrollEntrySerializer(updated_entries, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

