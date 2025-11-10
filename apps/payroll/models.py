from django.db import models
from decimal import Decimal
from django.conf import settings
from utils.validators import (
    year_validator,
    month_validator,
    currency_validator,
    positive_decimal_validator
)
from django.utils import timezone

class PayrollPeriod(models.Model):
    year = models.PositiveSmallIntegerField(validators=year_validator)
    month = models.PositiveSmallIntegerField(validators=month_validator)
    start_date = models.DateField()
    end_date = models.DateField()
    is_locked = models.BooleanField(default=False, db_index=True, help_text="No further edits allowed for this month, if locked")
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='locked_periods')
    
    class Meta:
        db_table = 'payroll_periods'
        unique_together = [("year", "month")]
        ordering = ["-year", "-month"]
        constraints = [
            models.CheckConstraint(
                name='payroll_period_valid_range',
                check=models.Q(end_date__gte=models.F('start_date')),
            )
        ]
        
    def __str__(self):
        return f"{self.year}-{self.month:02d}"
    
    @property
    def label(self):
        return f"{self.year}-{self.month:02d}"
    
    def lock(self, user=None):
        """Lock the payroll period"""
        if not self.is_locked:
            self.is_locked = True
            self.locked_at = timezone.now()
            self.locked_by = user
            self.save(update_fields=['is_locked', 'locked_at', 'locked_by'])
    
    def unlock(self):
        """Unlock the payroll period"""
        if self.is_locked:
            self.is_locked = False
            self.locked_at = None
            self.locked_by = None
            self.save(update_fields=['is_locked', 'locked_at', 'locked_by'])

    
class Compensation(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="salary")
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=positive_decimal_validator)
    currency = models.CharField(max_length=3, default="RON", validators=[currency_validator])
    
    class Meta:
        db_table = 'compensations'
    
    def __str__(self):
        return f"{self.user.full_name}: {self.amount} {self.currency}"
    
class Bonus(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bonuses")
    period = models.ForeignKey(PayrollPeriod, on_delete=models.PROTECT, related_name="bonuses")
    description = models.CharField(max_length=200, blank=True, default="")
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=positive_decimal_validator)
    
    class Meta:
        db_table = 'bonuses'
        indexes = [models.Index(fields=["period", "user"])]
        unique_together = [("user", "period", "description")]
    
    def __str__(self):
        return f"{self.user.full_name}: +{self.amount} in {self.period.label}"
    
class Payslip(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="payslips")
    period = models.ForeignKey(PayrollPeriod, on_delete=models.PROTECT, related_name="payslips")
    compensation = models.DecimalField(max_digits=12, decimal_places=2)
    unpaid_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    bonuses_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    net_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    calculated_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'payslips'
        indexes = [models.Index(fields=['period', 'user'])]
        unique_together = [("user", "period")]
        ordering = ['-period', 'user']
        
    def __str__(self):
        return f"Payslip: {self.user.full_name} - {self.period.label}"
    
   
    def calculate_net_total(self) -> Decimal:
        """Calculate and update net_total"""
        self.net_total = (
            (self.compensation or Decimal('0'))
            - (self.unpaid_deduction or Decimal('0'))
            + (self.bonuses_total or Decimal('0'))
        )
    def save(self, *args, **kwargs):
        self.calculate_net_total()
        super().save(*args, **kwargs)
    