import csv
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import logging

from django.conf import settings
from apps.accounts.models import User
from apps.payroll.models import PayrollPeriod, Compensation
from core.calculators.salary_calculator import SalaryCalculator

logger = logging.getLogger(__name__)

class CSVGenerationError(Exception):
    """Custom exception treatment for CSV generation errors"""
    def __init__(self, message:str, manager: Optional[User] = None, period: Optional[PayrollPeriod] = None, user: Optional[User] = None, original_exception: Optional[Exception] = None):
        self.message=message
        self.manager=manager
        self.period=period
        self.user=user
        self.original_exception=original_exception
        
        details = []
        
        if manager:
            details.append(f"Manager: {manager.full_name} (ID: {manager.id})")
        
        if period:
            details.append(f"Period: {period.label}")
        
        if user:
            details.append(f"User: {user.full_name} (ID: {user.id})")
        
        if original_exception:
            details.append(f"Original error: {str(original_exception)}")
        
        if details:
            full_message = f"{message} | {' | '.join(details)}"
        else:
            full_message = message
        
        logger.error(full_message, exc_info=original_exception)
        
        super().__init__(full_message)
    
    def __str__(self):
        return self.message
    
    def get_context(self) -> Dict:
        return {
            'message': self.message,
            'manager_id': self.manager.id if self.manager else None,
            'manager_name': self.manager.full_name if self.manager else None,
            'period_id': self.period.id if self.period else None,
            'period_label': self.period.label if self.period else None,
            'user_id': self.user.id if self.user else None,
            'user_name': self.user.full_name if self.user else None,
            'original_error': str(self.original_exception) if self.original_exception else None,
        }

class CSVGenerator:
    """
    Generate CSV reports for managers with employee salary data
    
    Format:
    -employee name
    -salary to be payd
    -working days
    -vacation days
    -bonuses
    -currency 
    """
    
    def __init__(self):
        self.calculator = SalaryCalculator()
        self.csv_directory = Path(settings.MEDIA_CSV_DIR)
        self.csv_directory.mkdir(parents=True, exist_ok=True)
        logger.info(f"CSVGenerator initialized with directory: {self.csv_directory}")
    
    def _generate_filename(self, manager: User, period: PayrollPeriod) -> str:
        """Generate a filename for report in format:
        manager_report_{manager_id}_{year}_{month}_{timestamp}"""
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"manager_report_{manager.id}_{period.year}_{period.month:02d}_{timestamp}.csv"
        logger.debug(f"Generated filename: {filename}")
        return filename
    
    
    def _prepare_user_data(self, user: User, period: PayrollPeriod) ->Dict:
        """Prepares employee data for CSV row"""
        try:
            breakdown = self.calculator.calculate(user, period)
            
            data = {
                'Employee Name': user.full_name,
                'Salary To Be Paid': str(breakdown.net_total),
                'Working Days': breakdown.business_days - breakdown.unpaid_days,
                'Vacation Days': self._get_vacation_days(user, period),
                'Bonuses': str(breakdown.bonuses_total),
                'Currency': self._get_currency(user),
            }
            logger.debug(f"Prepared data for {user.full_name}: Net={breakdown.net_total}")
            return data
        
        except Exception as e:
            raise CSVGenerationError(message=f"Failed to calculate salary for {user.full_name}", user=user, period=period,original_exception=e)
    def _get_vacation_days(self, user:User, period: PayrollPeriod) -> int:
        """get vacation days for a user in a specific period"""
        from apps.attendance.models import AttendanceRecord, AttendanceType
        
        vacation_days = AttendanceRecord.objects.filter(
            user=user, date__year=period.year, date__month=period.month,
            type=AttendanceType.VACATION
        ).count()
        
        logger.debug(f"Vacation days for {user.full_name}: {vacation_days}")
        
        return vacation_days
    
    def _get_currency(self, user:User) -> str:
        try:
            comp = Compensation.objects.get(user=user)
            return comp.currency 
        except Compensation.DoesNotExist:
            logger.warning(f"No compensation found for {user.full_name}, using default RON")
            return "RON"
    
    def generate_csv(self, manager: User,period: PayrollPeriod, employees: Optional[List[User]] = None) -> Path:
        """Generate CSV report for manager"""
        
        logger.info(f"Starting CSV generation for manager {manager.full_name} (ID: {manager.id}), period {period.label}")
        
        if not manager.is_manager:
            raise CSVGenerationError(
                message=f"User {manager.full_name} is not a manager", manager=manager, period=period)
        
        if employees is None:
            employees = list(manager.direct_reports.filter(is_active=True).order_by('last_name', 'first_name'))
        
        if not employees:
            raise CSVGenerationError( message=f"No employees found for manager {manager.full_name}", manager=manager, period=period)
        
        logger.info(f"Processing {len(employees)} employees")
        
        filename = self._generate_filename(manager, period)
        filepath = self.csv_directory / filename
        
        rows = []
        failed_users = []
        for employee in employees:
            try:
                row_data = self._prepare_user_data(employee, period)
                rows.append(row_data)
            except CSVGenerationError as e:
                logger.warning(f"Failed to prepare data for {employee.full_name}: {e.message}")
                failed_users.append(employee.full_name)
                continue
            
        if not rows:
            raise CSVGenerationError(message="No valid employee data to generate CSV", manager=manager, period=period)
        
        if failed_users:
            logger.warning(f"Failed to process {len(failed_users)} employees: {', '.join(failed_users)}")
        
        
        fieldnames=[
            'Employee Name',
            'Salary To Be Paid',
            'Working Days',
            'Vacation Days',
            'Bonuses',
            'Currency',
        ]
        
        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            logger.info(f"CSV file generated successfully: {filepath} ({len(rows)} rows)")
        except Exception as e:
            raise CSVGenerationError( message=f"Failed to write CSV file: {str(e)}", manager=manager, period=period, original_exception=e)
        return filepath
    
    def generate_csv_for_team(self, manager: User, period: PayrollPeriod, include_indirect: bool = False)-> Path:
        logger.info(f"Generating CSV for team (include_indirect={include_indirect})")
        if include_indirect:
            employees = manager.get_all_subordinates(include_indirect=True)
        else:
            employees = manager.direct_reports.filter(is_active=True)
        
        employees = employees.order_by('last_name', 'first_name')
        
        return self.generate_csv(manager, period, list(employees))
    
    def generate_csv_content(self, manager: User, period: PayrollPeriod, employees: Optional[List[User]] = None) -> str:
        """Generate csv and save it as string for in memory operations"""
        import io
        
        logger.info(f"Generating CSV content in-memory for manager {manager.full_name}")

        if not manager.is_manager:
            raise CSVGenerationError(message=f"User {manager.full_name} is not a manager",manager=manager,period=period)
        if employees is None:
            employees = manager.direct_reports.filter(is_active=True).order_by('last_name', 'first_name')
        if not employees:
            raise CSVGenerationError(message=f"No employees found for manager {manager.full_name}",manager=manager,period=period)
        
        
        rows = []
        for employee in employees:
            try:
                row_data = self._prepare_user_data(employee, period)
                rows.append(row_data)
            except CSVGenerationError as e:
                logger.warning(f"Failed to prepare data for {employee.full_name}: {e.message}")
                continue
        
        if not rows:
            raise CSVGenerationError("No valid employee data to generate CSV")
        
        fieldnames = [
            'Employee Name',
            'Salary To Be Paid',
            'Working Days',
            'Vacation Days',
            'Bonuses',
            'Currency'
        ]
        
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        
        content = output.getvalue()
        logger.info(f"CSV content generated successfully ({len(rows)} rows, {len(content)} bytes)")
        return content

__all__ = [
    'CSVGenerator',
    'CSVGenerationError',
]