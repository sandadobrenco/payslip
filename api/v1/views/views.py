from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.db.models import Q
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from pathlib import Path

from ..serializers.user_serializers import UserSerializer
from ..serializers.attendance_serializers import AttendanceRecordSerializer

from ..serializers.payroll_serializers import (
    PayrollPeriodSerializer,
    CompensationSerializer,
    BonusSerializer
)
from ..serializers.report_serializers import (
    CreateAggregatedDataSerializer,
    SendAggregatedDataSerializer,
    CreatePdfSerializer,
    SendPdfSerializer,
)

from ..permissions import (
    IsManagerOnly, is_top_manager
)

from core.services.email_service import EmailService
from core.generators.csv_generator import CSVGenerator
from core.generators.pdf_generator import PDFGenerator

from django.contrib.auth import get_user_model
from apps.attendance.models import AttendanceRecord
from apps.payroll.models import PayrollPeriod, Compensation, Bonus
from apps.reports.models import GeneratedReport, ReportType

from django.conf import settings
User = get_user_model()

class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, IsManagerOnly]

    def get_queryset(self):
        u = self.request.user
        if is_top_manager(u):
            return User.objects.all()
        return User.objects.filter(Q(id=u.id) | Q(manager=u))


class AttendanceRecordViewSet(viewsets.ModelViewSet):
    serializer_class = AttendanceRecordSerializer
    permission_classes = [IsAuthenticated, IsManagerOnly]
    http_method_names = ['get', 'post', 'put', 'patch']

    def get_queryset(self):
        u = self.request.user
        qs = AttendanceRecord.objects.select_related("user")
        if is_top_manager(u):
            return qs
        return qs.filter(Q(user=u) | Q(user__manager=u))
    def destroy(self, request, *args, **kwargs):
        return Response({'detail': 'Deleting attendance is not allowed.'}, status=405)

class PayrollPeriodViewSet(viewsets.ModelViewSet):
    serializer_class = PayrollPeriodSerializer
    permission_classes = [IsAuthenticated, IsManagerOnly]
    queryset = PayrollPeriod.objects.all().order_by("-year", "-month")


class CompensationViewSet(viewsets.ModelViewSet):
    serializer_class = CompensationSerializer
    permission_classes = [IsAuthenticated, IsManagerOnly]
    def get_queryset(self):
        u = self.request.user
        qs = Compensation.objects.select_related("user")
        return qs if is_top_manager(u) else qs.filter(user__manager=u)


class BonusViewSet(viewsets.ModelViewSet):
    serializer_class = BonusSerializer
    permission_classes = [IsAuthenticated, IsManagerOnly]
    def get_queryset(self):
        u = self.request.user
        qs = Bonus.objects.select_related("user", "period")
        return qs if is_top_manager(u) else qs.filter(user__manager=u)


class CreateAggregatedEmployeeData(APIView):
    permission_classes = [IsAuthenticated, IsManagerOnly]

    def post(self, request):
        serializer = CreateAggregatedDataSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        period = serializer.validated_data["period"]
        user_ids = serializer.validated_data.get("user_ids")
        
        if user_ids:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            employees_qs = User.objects.filter(id__in=user_ids, is_active=True)
            employees = list(employees_qs.order_by("last_name", "first_name"))
            CSVGenerator().generate_csv(request.user, period, employees=employees)
        else:
            CSVGenerator().generate_csv_for_team(request.user, period, include_indirect=False)
    
        return Response({"detail": "CSV generated"}, status=status.HTTP_201_CREATED)


class SendAggregatedEmployeeData(APIView):
    permission_classes = [IsAuthenticated, IsManagerOnly]

    def post(self, request):
        serializer = SendAggregatedDataSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        
        period = serializer.validated_data["period"]
        include_indirect = serializer.validated_data.get("include_indirect", True)
        
        EmailService().queue_csv_to_manager(request.user, period, include_indirect=include_indirect)
        return Response({"detail": "CSV queued for sending"}, status=status.HTTP_202_ACCEPTED)


class CreatePdfForEmployees(APIView):
    permission_classes = [IsAuthenticated, IsManagerOnly]

    def post(self, request):
        user_ids = request.data.get("user_ids")
        period_id = request.data.get("period")
        if not period_id:
            return Response({"detail": "period is required"}, status=400)
        period = get_object_or_404(PayrollPeriod, id=period_id)

        if user_ids:
            for uid in user_ids:
                s = CreatePdfSerializer(data={"period": period.id, "user_id": uid}, context={"request": request})
                s.is_valid(raise_exception=True)
                u = get_object_or_404(User, id=uid)
                pdf_path = PDFGenerator().generate_pdf(u, period)
                rel = pdf_path.relative_to(Path(settings.MEDIA_ROOT))
                GeneratedReport.objects.update_or_create(
                    type=ReportType.USER_PDF,
                    period=period,
                    user=u,
                    defaults={"file": str(rel), "file_format": "pdf"},
                )
        else:
            s = CreatePdfSerializer(data=request.data, context={"request": request})
            s.is_valid(raise_exception=True)
            u = get_object_or_404(User, id=s.validated_data["user_id"])
            pdf_path = PDFGenerator().generate_pdf(u, period)
            rel = pdf_path.relative_to(Path(settings.MEDIA_ROOT))
            GeneratedReport.objects.update_or_create(
                type=ReportType.USER_PDF,
                period=period,
                user=u,
                defaults={"file": str(rel), "file_format": "pdf"},
            )
        return Response({"detail": "PDF(s) generated"}, status=status.HTTP_201_CREATED)


class SendPdfToEmployees(APIView):
    permission_classes = [IsAuthenticated, IsManagerOnly]

    def post(self, request):
        s = SendPdfSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        report = GeneratedReport.objects.select_related("user", "period").get(id=s.validated_data["report_id"]) 
        EmailService().send_payslip_for_manager(request.user, report.period, report=report,
                                         to_email=s.validated_data.get("email"),
                                         subject=s.validated_data.get("subject"))
        return Response({"detail": "PDF sent"}, status=status.HTTP_200_OK)
