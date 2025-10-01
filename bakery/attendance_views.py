"""Attendance-related API viewsets."""

from django.utils.dateparse import parse_date
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import Employee, Attendance
from .serializers import EmployeeSerializer, AttendanceSerializer


class EmployeeViewSet(viewsets.ModelViewSet):
    """CRUD endpoints for managing bakery employees."""

    queryset = Employee.objects.select_related("outlet").all()
    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated]


class AttendanceViewSet(viewsets.ModelViewSet):
    """CRUD endpoints for employee attendance entries."""

    queryset = Attendance.objects.select_related("employee", "employee__outlet").all()
    serializer_class = AttendanceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params

        date_from = parse_date(params.get("date_from")) if params.get("date_from") else None
        if date_from:
            qs = qs.filter(date__gte=date_from)

        date_to = parse_date(params.get("date_to")) if params.get("date_to") else None
        if date_to:
            qs = qs.filter(date__lte=date_to)

        employee_id = params.get("employee_id")
        if employee_id:
            qs = qs.filter(employee_id=employee_id)

        outlet_id = params.get("outlet_id")
        if outlet_id:
            qs = qs.filter(employee__outlet_id=outlet_id)

        return qs.order_by("-date", "-created_at")
