from django.db import models
from apps.payroll.models import PayrollPeriod
from django.conf import settings
from django.utils import timezone

class ReportType(models.TextChoices):
    MANAGER_CSV = "MANAGER_CSV", "CSV aggregated per manager"
    USER_PDF = "USER_PDF", "PDF per employee"
    
def report_upload_path(instance, filename: str) -> str:
    period_label = instance.period.label if instance.period_id else 'adhoc'
    if instance.type == ReportType.MANAGER_CSV:
        identifier = f"manager_{instance.manager_id or 'unknown'}"
    else:
        identifier = f"user_{instance.user_id or 'unknown'}"
    
    return f"reports/{period_label}/{instance.type}/{identifier}/{filename}"

class GeneratedReport(models.Model):
    """A file generated in CSV format if a manager triggers reports generation,
    or a PDF format file if it is generated for an employee."""
    type = models.CharField(max_length=20, choices=ReportType.choices)
    period = models.ForeignKey(PayrollPeriod, on_delete=models.PROTECT, related_name="reports")
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="manager_reports")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="employee_reports")
    file = models.FileField(upload_to=report_upload_path)
    file_format = models.CharField(max_length=50, blank=True, null=True, help_text="File extension (csv, pdf)")
    users_included = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="included_in_reports")
    sent_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)
    
    class Meta:
        db_table = 'generated_reports'
        indexes = [
            models.Index(fields=["type", "period", "manager"]),
            models.Index(fields=['type', 'period', 'user']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["type", "period", "manager"],
                name="unique_manager_report_per_period",
                condition=models.Q(type=ReportType.MANAGER_CSV, archived_at__isnull=True),
            ),
            models.UniqueConstraint(
                fields=["type", "period", "user"],
                name="unique_user_report_per_period",
                condition=models.Q(type=ReportType.USER_PDF, archived_at__isnull=True),
            ),
            models.CheckConstraint(
                name="report_csv_requires_manager",
                check=models.Q(type=ReportType.MANAGER_CSV, manager__isnull=False, user__isnull=True)
                    | models.Q(type=ReportType.USER_PDF),
            ),
            models.CheckConstraint(
                name="report_pdf_requires_employee",
                check=models.Q(type=ReportType.USER_PDF, user__isnull=False, manager__isnull=True)
                    | models.Q(type=ReportType.MANAGER_CSV),
            ),
        ]
        ordering = ['-sent_at']
        
    def __str__(self):
        target = self.manager if self.type == ReportType.MANAGER_CSV else self.user
        recipient  = target.full_name if target else "Unknown"
        return f"{self.get_type_display()} - {self.period.label} → {recipient}"
    
    @property
    def is_sent(self) -> bool:
        return self.sent_at is not None

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None
    
    def mark_sent(self):
        self.sent_at = timezone.now()
        self.save(update_fields=["sent_at"])
    
    def mark_archived(self):
        self.archived_at = timezone.now()
        self.save(update_fields=["archived_at"])

class EmailStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    SENT = "SENT", "Sent"
    FAILED = "FAILED", "Failed"
    
class EmailLog(models.Model):
    report = models.ForeignKey(GeneratedReport, on_delete=models.CASCADE, related_name="email_logs")
    to_email = models.EmailField()
    subject = models.CharField(max_length=200)
    status = models.CharField(max_length=10, choices=EmailStatus.choices, default=EmailStatus.PENDING, db_index=True)
    error_message = models.TextField(blank=True,help_text="Error message if sending failed")
    sent_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0,help_text="Number of send attempts")
    
    class Meta:
        db_table = 'email_logs'
        indexes = [
            models.Index(fields=['status', 'sent_at']),
            models.Index(fields=['to_email']),
        ]
        ordering = ['-sent_at']
    
    def __str__(self):
        return f"{self.get_status_display()} → {self.to_email} (Report #{self.report_id})"
    
    def mark_sent(self):
        self.status = EmailStatus.SENT
        self.sent_at = timezone.now()
        self.attempts += 1
        self.save(update_fields=['status', 'sent_at', 'attempts'])
    
    def mark_failed(self, error_message: str = ''):
        self.status = EmailStatus.FAILED
        self.error_message = error_message
        self.attempts += 1
        self.save(update_fields=['status', 'error_message', 'attempts'])
                
            
    
    
