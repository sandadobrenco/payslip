from django.db import models
from decimal import Decimal
from django.conf import settings
from apps.payroll.models import PayrollPeriod
from utils.validators import (
    day_hours_validator,
    day_validator,
    day_extended_validator,
    year_validator,
    month_hours_validator
)


class AttendanceType(models.TextChoices):
    WORKED = "WORKED", "Worked"
    VACATION = "VACATION", "Vacation"
    SICK_LEAVE = "SICK_LEAVE", "Sick Leave"
    UNPAID_LEAVE = "UNPAID_LEAVE", "Unpaid Leave"
    PUBLIC_HOLIDAY = "PUBLIC_HOLIDAY", "Public Holiday"


class AttendanceRecord(models.Model):
    """Daily attendance record for each employee"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="attendance_records")
    date = models.DateField(db_index=True)
    type = models.CharField(max_length=20, choices=AttendanceType.choices, default=AttendanceType.WORKED)
    hours_worked = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("8.00"),
        validators=day_hours_validator,
        help_text="Number of hours worked")

    class Meta:
        db_table = 'attendance_records'
        indexes = [
            models.Index(fields=["user", "date"]),
            models.Index(fields=["date"]),
            models.Index(fields=["type"]),
        ]
        unique_together = [("user", "date")]
        ordering = ["-date", "user"]
        constraints = [
            models.CheckConstraint(
                name="valid_hours_for_vacation",
                check=models.Q(type=AttendanceType.VACATION, hours_worked=0)
                    | ~models.Q(type=AttendanceType.VACATION),
            ),
            models.CheckConstraint(
                name="valid_hours_for_unpaid_leave",
                check=models.Q(type=AttendanceType.UNPAID_LEAVE, hours_worked=0)
                    | ~models.Q(type=AttendanceType.UNPAID_LEAVE),
            ),
            models.CheckConstraint(
            name="valid_hours_for_public_holiday",
            check=models.Q(type=AttendanceType.PUBLIC_HOLIDAY, hours_worked=0) | ~models.Q(type=AttendanceType.PUBLIC_HOLIDAY),
            ),
        ]

    def __str__(self):
        return f"{self.user.full_name} - {self.date} ({self.type})"

    @property
    def is_working_day(self) -> bool:
        return self.type == AttendanceType.WORKED

    @property
    def is_paid_leave(self) -> bool:
        return self.type in [
            AttendanceType.VACATION,
            AttendanceType.SICK_LEAVE,
            AttendanceType.PUBLIC_HOLIDAY,
        ]


class MonthlyAttendanceSummary(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="monthly_attendance")
    period = models.ForeignKey(PayrollPeriod, on_delete=models.PROTECT, related_name="attendance_summaries")
    total_working_days = models.PositiveSmallIntegerField(default=0, validators=day_validator)
    total_vacation_days = models.PositiveSmallIntegerField(default=0, validators=day_validator)
    total_sick_days = models.PositiveSmallIntegerField(default=0, validators=day_validator)
    total_unpaid_days = models.PositiveSmallIntegerField(default=0, validators=day_validator)
    total_hours_worked = models.DecimalField( max_digits=6, decimal_places=2, default=Decimal("0.00"), validators=month_hours_validator)
    public_holiday_days = models.PositiveIntegerField(default=0, validators=day_validator)
     
    class Meta:
        db_table = 'monthly_attendance_summaries'
        indexes = [
            models.Index(fields=["user", "period"]),
            models.Index(fields=["period"]),
        ]
        unique_together = [("user", "period")]
        ordering = ["-period", "user"]

    def __str__(self):
        return f"{self.user.full_name} - {self.period.label} Summary"

    @classmethod
    def calculate_for_user_period(cls, user, period):
        """Calculate and save attendance summary for a user in a given period.
        Returns the MonthlyAttendanceSummary instance.
        """
        records = AttendanceRecord.objects.filter(
            user=user,
            date__range=[period.start_date, period.end_date]
        )

        summary, created = cls.objects.update_or_create(
            user=user,
            period=period,
            defaults={
                'total_working_days': records.filter(
                    type=AttendanceType.WORKED
                ).count(),
                'total_vacation_days': records.filter(
                    type=AttendanceType.VACATION
                ).count(),
                'total_sick_days': records.filter(
                    type=AttendanceType.SICK_LEAVE
                ).count(),
                'total_unpaid_days': records.filter(
                    type=AttendanceType.UNPAID_LEAVE
                ).count(),
                'public_holiday_days': records.filter(
                    type=AttendanceType.PUBLIC_HOLIDAY
                ).count(),
                'total_hours_worked': sum(
                    record.hours_worked or Decimal('0')
                    for record in records.filter(type=AttendanceType.WORKED)
                )
            }
        )

        return summary


class VacationBalance(models.Model):
    """Track vacation days balance for each employee per year"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="vacation_balances")
    year = models.PositiveSmallIntegerField(validators=year_validator)
    total_days_allocated = models.PositiveSmallIntegerField(default=21,validators=day_validator,help_text="Total vacation days allocated for the year")
    days_used = models.PositiveSmallIntegerField(default=0,validators=day_validator)
    days_carried_over = models.SmallIntegerField(default=0,validators=day_extended_validator,help_text="Days carried over from previous year (can be negative)")

    class Meta:
        db_table = 'vacation_balances'
        indexes = [
            models.Index(fields=["user", "year"]),
            models.Index(fields=["year"]),
        ]
        unique_together = [("user", "year")]
        ordering = ["-year", "user"]

    def __str__(self):
        return f"{self.user.full_name} - {self.year} Vacation Balance"

    @property
    def days_remaining(self) -> int:
        """Calculate remaining vacation days"""
        return (self.total_days_allocated + self.days_carried_over) - self.days_used

    @property
    def days_available(self) -> int:
        """Total days available (allocated + carried over)"""
        return self.total_days_allocated + self.days_carried_over

    def update_used_days(self):
        """Update days_used from attendance records"""
        vacation_count = AttendanceRecord.objects.filter(
            user=self.user,
            date__year=self.year,
            type=AttendanceType.VACATION
        ).count()
        
        self.days_used = vacation_count
        self.save(update_fields=["days_used"])