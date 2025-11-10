from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence
import logging
from django.utils import timezone

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.template.loader import render_to_string
from django.template import TemplateDoesNotExist
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.reports.models import GeneratedReport, ReportType
from apps.payroll.models import PayrollPeriod

from core.generators.csv_generator import CSVGenerator, CSVGenerationError
from core.generators.pdf_generator import PDFGenerator, PDFGenerationError
from core.services.archive_service import ArchiveService, ArchiveServiceError

from utils.constants import (
    TPL_MANAGER_CSV, TPL_EMPLOYEE_PDF,
    EMAIL_SUBJECT_MANAGER_REPORT, EMAIL_SUBJECT_EMPLOYEE_PAYSLIP,)

logger = logging.getLogger(__name__)

CELERY_AVAILABLE = False
try:
    from celery import shared_task
    CELERY_AVAILABLE = True
except Exception:
    CELERY_AVAILABLE = False

CELERY_ENABLED = CELERY_AVAILABLE and getattr(settings, "ENABLE_CELERY", False)

@dataclass
class EmailResult:
    recipient: str
    attachments: Sequence[Path]
    status: Optional[int]  

class EmailServiceError(Exception):
    def __init__(self, message: str, *, context: Optional[dict] = None) -> None:
        super().__init__(message)
        self.message = message
        self.context = context or {}
    def get_context(self) -> dict: return self.context

class EmailService:
    """Mail CSV to manager and payslip PDFs to employees with immediate archiving."""

    def __init__(self, *, from_email: Optional[str] = None) -> None:
        self.from_email = from_email or getattr(settings, "DEFAULT_FROM_EMAIL", None)
        if not self.from_email:
            raise EmailServiceError("DEFAULT_FROM_EMAIL is not configured.")
        self._csv = CSVGenerator()
        self._pdf = PDFGenerator()
        self._archive = ArchiveService()
        logger.info(f"EmailService initialized with from_email: {self.from_email}")

    def _render(self, template: str, ctx: dict, fallback: str) -> str:
        try:
            return render_to_string(template, ctx).strip()
        except TemplateDoesNotExist:
            return fallback.format(**ctx)

    def _send(self, *, to: str, subject: str, body: str, attachments: Sequence[Path]) -> EmailResult:
        msg = EmailMessage(subject=subject, body=body, from_email=self.from_email, to=[to])
        for path in attachments:
            msg.attach_file(str(path))
        status = msg.send(fail_silently=False)
        logger.info("Sent email", extra={"to": to, "subject": subject, "attachments": [str(p) for p in attachments], "status": status})
        return EmailResult(recipient=to, attachments=attachments, status=status)

    @transaction.atomic
    def send_csv_to_manager(self, manager: User, period: PayrollPeriod, *, include_indirect: bool = True) -> EmailResult:
        """Generate CSV, mail it to manager, then archive immediately"""
        logger.info(f"Starting CSV generation and email for manager {manager.full_name} (ID: {manager.id}), period {period.label}") 
        
        try:
            csv_path = self._csv.generate_csv_for_team(manager, period, include_indirect=include_indirect)
        except CSVGenerationError as e:
            raise EmailServiceError("CSV generation failed.", context=e.get_context()) from e
        
        try:
            rel = csv_path.relative_to(Path(settings.MEDIA_ROOT))
        except Exception:
            rel = csv_path
        report, _ = GeneratedReport.objects.update_or_create(
            type=ReportType.MANAGER_CSV,
            period=period,
            manager=manager,
            defaults={"file": str(rel), "file_format": "csv"},
        )

        subject = EMAIL_SUBJECT_MANAGER_REPORT.format(period=period.label)
        body = self._render(TPL_MANAGER_CSV, {"full_name": manager.full_name, "period_label": period.label},
                            fallback="Dear {full_name},\n\nYour salary report for {period_label} is attached")

        try:
            result = self._send(to=manager.email, subject=subject, body=body, attachments=[csv_path])
        except Exception as e:
            raise EmailServiceError("Sending CSV email failed.", context={"manager": manager.id}) from e
        
        try:
            if hasattr(report, "mark_sent"):
                report.mark_sent()
            else:
                report.sent_at = timezone.now()
                report.save(update_fields=["sent_at"])
        except Exception:
            logger.exception("Could not mark report as sent", extra={"report_id": report.id})
            
        try:
            self._archive.archive_files([csv_path], label=f"csv_{manager.id}", period=period)
        except ArchiveServiceError:
            logger.exception("Archiving CSV failed", extra={"manager": manager.id})
        
        try:
            if hasattr(report, "mark_archived"):
                report.mark_archived()
            else:
                report.archived_at = timezone.now()
                report.save(update_fields=["archived_at"])
        except Exception:
            logger.exception("Could not mark report as archived", extra={"report_id": report.id})
        return result

    def queue_csv_to_manager(self, manager: User, period: PayrollPeriod, *, include_indirect: bool = True) -> EmailResult:
        if CELERY_ENABLED:
            logger.info(f"Queuing CSV email to manager {manager.full_name} (ID: {manager.id})") 
            task_send_csv_to_manager.delay(manager.id, period.id, include_indirect)
            return EmailResult(recipient=manager.email, attachments=[], status=None)
        logger.info(f"Sending CSV immediately (Celery disabled)")
        return self.send_csv_to_manager(manager, period, include_indirect=include_indirect)

    @transaction.atomic
    def send_payslip_for_manager(self, manager: User, period: PayrollPeriod, *, report: GeneratedReport | None = None, user: User | None = None, to_email: str | None = None, subject: str | None = None,) -> str:
        """Generate and send password-protected PDFs to each employee, archiving each right after send"""
        logger.info(f"Starting payslip email generation for manager {manager.full_name} team") 
        if report is not None:
            if report.type != ReportType.USER_PDF:
                raise EmailServiceError("Report must be USER_PDF", context={"report_id": report.id})
            employee = report.user
            period = report.period or period
        else:
            if user is None:
                raise EmailServiceError("Provide either `report` or `user`.", context={"manager_id": manager.id})
            employee = user
        
        if not employee or not employee.email:
            raise EmailServiceError("Employee email is missing", context={"user_id": getattr(employee, "id", None)})

        pdf_path: Path | None = None
        if report is not None and getattr(report, "file", None):
            try:
                candidate = Path(report.file.path)
                if candidate.exists():
                    pdf_path = candidate
            except Exception:
                pdf_path = None
        if pdf_path is None:
            pdf_path = self._pdf.generate_pdf(employee, period)
            if report is not None:
                try:
                    rel = pdf_path.relative_to(settings.MEDIA_ROOT)
                    report.file.name = str(rel)
                    report.save(update_fields=["file"])
                except Exception:
                    pass
        try:
            body = self._render(TPL_EMPLOYEE_PDF, {"full_name": employee.full_name, "period_label": period.label},
                                fallback="Dear {full_name},\n\nYour payslip for {period_label} is attached.")
        except TemplateDoesNotExist:
            body = f"Dear {getattr(employee, 'full_name', str(employee))},\n\nYour payslip for {period.label} is attached."

        final_subject = subject or EMAIL_SUBJECT_EMPLOYEE_PAYSLIP.format(period=period.label)
        recipient = to_email or employee.email
        
        self._send(to=recipient, subject=final_subject, body=body, attachments=[pdf_path])
        
        label = f"pdf_{getattr(manager, 'id', 0)}_{employee.id}"
        try:
            self._archive.archive_files([pdf_path], label=label, period=period)
        except Exception as e:
            logging.exception("Archiving PDF failed", extra={"employee": employee.id, "period": period.id})

        try:
            if report is not None and hasattr(report, "mark_sent"):
                report.mark_sent()
            if report is not None and hasattr(report, "mark_archived"):
                report.mark_archived()
        except Exception:
            pass

        return recipient

if CELERY_ENABLED:
    @shared_task(bind=True)
    def task_send_csv_to_manager(self, manager_id: int, period_id: int, include_indirect: bool = True) -> str:
        from apps.payroll.models import PayrollPeriod
        
        manager = User.objects.get(pk=manager_id)
        period = PayrollPeriod.objects.get(pk=period_id)
        EmailService().send_csv_to_manager(manager, period, include_indirect=include_indirect)
        return f"CSV mailed to {manager.email}"
