from __future__ import annotations
from datetime import date, timedelta
from decimal import Decimal

from dataclasses import dataclass

from django.db import transaction
from django.db.models import Sum

from apps.payroll.models import PayrollPeriod, Compensation, Bonus, Payslip
from apps.attendance.models import AttendanceRecord, AttendanceType
from utils.constants import MONEY_QUANT, MONEY_ROUNDING

def _quantize_money(value: Decimal) -> Decimal:
    return (value or Decimal("0")).quantize(MONEY_QUANT, rounding=MONEY_ROUNDING)

def count_business_days(start: date, end:date) -> int:
    """Count business days between certain dates"""
    if start > end:
        return 0 
    days = 0 
    cur = start
    one_day = timedelta(days=1)
    while cur <= end:
        if cur.weekday() < 5:
            days += 1
        cur += one_day
    return days

@dataclass(frozen=True)
class SalaryBreakdown:
    compensation : Decimal
    bonuses_total: Decimal
    unpaid_deduction: Decimal
    net_total: Decimal
    business_days: int
    unpaid_days: int

class SalaryCalculator:
    """Salary operations calculation for a user in a payroll period"""
    
    def __init__(self, *, default_daily_hours: Decimal = Decimal("8.00")) -> None:
        self.default_daily_hours = default_daily_hours
    
    def _get_compensation(self, user) -> Compensation:
        try:
            return Compensation.objects.get(user=user)
        except Compensation.DoesNotExist:
            raise ValueError(f"No compensation found for user {getattr(user,'full_name', user)}")
    
    def _count_unpaid_days(self, user, period: PayrollPeriod) -> int:
        return AttendanceRecord.objects.filter(
            user=user,
            date__range=(period.start_date, period.end_date),
            type=AttendanceType.UNPAID_LEAVE
        ).count()
    
    def _sum_bonuses(self, user, period: PayrollPeriod) -> Decimal:
        agg = Bonus.objects.filter(user=user, period=period).aggregate(total=Sum("amount"))
        return _quantize_money(agg.get("total") or Decimal("0"))
    
    def _daily_rate(self, monthly_amount: Decimal, business_days: int) -> Decimal:
        if business_days <= 0:
            return Decimal("0")
        return (monthly_amount / Decimal(business_days)).quantize(MONEY_QUANT, rounding=MONEY_ROUNDING)
    
    def calculate(self, user, period: PayrollPeriod) -> SalaryBreakdown:
        
        comp = self._get_compensation(user)
        business_days = count_business_days(period.start_date, period.end_date)
        unpaid_days = self._count_unpaid_days(user, period)
        
        daily_rate = self._daily_rate(comp.amount, business_days)
        unpaid_deduction = _quantize_money(daily_rate * Decimal(unpaid_days))
        bonuses_total = self._sum_bonuses(user,period)
        
        net_total = (comp.amount - unpaid_deduction + bonuses_total).quantize(MONEY_QUANT, rounding=MONEY_ROUNDING)
        
        return SalaryBreakdown(
            compensation=_quantize_money(comp.amount),
            bonuses_total=bonuses_total,
            unpaid_deduction=unpaid_deduction,
            net_total=net_total,
            business_days=business_days,
            unpaid_days=unpaid_days,
        )
    
    @transaction.atomic
    def generate_payslip(self, user, period: PayrollPeriod) -> Payslip:
        if period.is_locked:
            raise ValueError(f"Can't generate payslip for locked period {period.label}")
        
        if Payslip.objects.filter(user=user, period=period).exists():
            raise ValueError(f"Payslip already exists for {getattr(user, 'full_name', user)} in {period.label}")
        
        breakdown = self.calculate(user, period)
        
        slip = Payslip(
            user=user,
            period=period,
            compensation=breakdown.compensation,
            unpaid_deduction=breakdown.unpaid_deduction,
            bonuses_total=breakdown.bonuses_total,
        )
        slip.save()
        return slip
    def calculate_for_team(self, manager, period: PayrollPeriod, include_indirect: bool = False) -> list[dict]:
        """
        Calculate salaries for all employees under a manager.
        """
        if not manager.is_manager:
            raise ValueError(f"User {manager.full_name} is not a manager")
        
        if include_indirect:
            employees = manager.get_all_subordinates(include_indirect=True)
        else:
            employees = manager.direct_reports.filter(is_active=True)
        
        results = []
        for emp in employees:
            try:
                breakdown = self.calculate(emp, period)
                results.append({
                    'user': emp,
                    'breakdown': breakdown,
                    'error': None
                })
            except Exception as e:
                results.append({
                    'user': emp,
                    'breakdown': None,
                    'error': str(e)
                })
        
        return results
    
__all__ = [
    "SalaryCalculator",
    "SalaryBreakdown",
    "count_business_days",
]
