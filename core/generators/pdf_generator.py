import subprocess
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List

from django.conf import settings
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle

from apps.accounts.models import User
from apps.payroll.models import PayrollPeriod, Compensation
from core.calculators.salary_calculator import SalaryCalculator, SalaryBreakdown

logger = logging.getLogger(__name__)


class PDFGenerationError(Exception):
    """Custom exception for PDF generation errors with context and logging."""
    def __init__(
        self,
        message: str,
        user: Optional[User] = None,
        period: Optional[PayrollPeriod] = None,
        manager: Optional[User] = None,
        original_exception: Optional[Exception] = None
    ):
        self.message = message
        self.user = user
        self.period = period
        self.manager = manager
        self.original_exception = original_exception
        
       
        details = []
        
        if user:
            details.append(f"User: {user.full_name} (ID: {user.id})")
        
        if period:
            details.append(f"Period: {period.label}")
        
        if manager:
            details.append(f"Manager: {manager.full_name} (ID: {manager.id})")
        
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
        """Get error context as dictionary"""
        return {
            'message': self.message,
            'user_id': self.user.id if self.user else None,
            'user_name': self.user.full_name if self.user else None,
            'period_id': self.period.id if self.period else None,
            'period_label': self.period.label if self.period else None,
            'manager_id': self.manager.id if self.manager else None,
            'manager_name': self.manager.full_name if self.manager else None,
            'original_error': str(self.original_exception) if self.original_exception else None,
        }


class PDFGenerator:
    """Generates password-protected PDF payslips for employees"""
    
    def __init__(self):
        self.calculator = SalaryCalculator()
        self.pdf_dir = Path(settings.MEDIA_PDF_DIR)
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self.page_width, self.page_height = A4
        logger.info(f"PDFGenerator initialized with directory: {self.pdf_dir}")
    
    def _generate_filename(self, user: User, period: PayrollPeriod, temp: bool = False) -> str:
        """Generate unique filename for PDF payslip"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        prefix = 'temp_' if temp else ''
        filename = f"{prefix}payslip_{user.id}_{period.year}_{period.month:02d}_{timestamp}.pdf"
        logger.debug(f"Generated filename: {filename}")
        return filename
    
    def _draw_header(self, c: canvas.Canvas, user: User, period: PayrollPeriod):
        """Draw PDF header with title and company info"""
        logger.debug(f"Drawing header for {user.full_name}")
        
        c.setFont("Helvetica-Bold", 20)
        c.drawString(2*cm, self.page_height - 3*cm, "PAYSLIP")
        
        c.setFont("Helvetica", 12)
        c.drawString(2*cm, self.page_height - 3.8*cm, f"Period: {period.year}-{period.month:02d}")
        c.drawString(2*cm, self.page_height - 4.4*cm, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        
        c.setStrokeColor(colors.grey)
        c.setLineWidth(1)
        c.line(2*cm, self.page_height - 5*cm, self.page_width - 2*cm, self.page_height - 5*cm)
    
    def _draw_employee_details(self, c: canvas.Canvas, user: User, y_start: float):
        """Draw employee personal information"""
        logger.debug(f"Drawing employee details for {user.full_name}")
        
        c.setFont("Helvetica-Bold", 14)
        c.drawString(2*cm, y_start, "EMPLOYEE INFORMATION")
        
        c.setFont("Helvetica", 11)
        y = y_start - 0.8*cm
        
        details = [
            ("Name:", user.full_name),
            ("Employee ID:", str(user.id)),
            ("CNP:", user.cnp),
            ("Email:", user.email),
        ]
        
        for label, value in details:
            c.setFont("Helvetica-Bold", 10)
            c.drawString(2*cm, y, label)
            c.setFont("Helvetica", 10)
            c.drawString(5*cm, y, value)
            y -= 0.6*cm
        
        return y - 0.5*cm
    
    def _draw_salary_table(self, c: canvas.Canvas, breakdown: SalaryBreakdown, currency: str, y_start: float):
        """Draw salary breakdown table"""
        logger.debug(f"Drawing salary table: Net={breakdown.net_total} {currency}")
        
        c.setFont("Helvetica-Bold", 14)
        c.drawString(2*cm, y_start, "SALARY BREAKDOWN")
        
        data = [
            ['Description', 'Amount'],
            ['Base Compensation', f"{breakdown.compensation:,.2f} {currency}"],
            ['Bonuses', f"+{breakdown.bonuses_total:,.2f} {currency}"],
        ]
        
        if breakdown.unpaid_deduction > 0:
            data.append(['Unpaid Leave Deduction', f"-{breakdown.unpaid_deduction:,.2f} {currency}"])
        
        data.append(['', '']) 
        data.append(['NET TOTAL', f"{breakdown.net_total:,.2f} {currency}"])
        
        table = Table(data, colWidths=[10*cm, 6*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            
            ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -2), 10),
            ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
            ('TOPPADDING', (0, 1), (-1, -2), 8),
            ('BOTTOMPADDING', (0, 1), (-1, -2), 8),
            
            ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, -1), (-1, -1), 14),
            ('TOPPADDING', (0, -1), (-1, -1), 12),
            ('BOTTOMPADDING', (0, -1), (-1, -1), 12),
            
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('BOX', (0, 0), (-1, -1), 2, colors.black),
        ]))
        
        table.wrapOn(c, self.page_width, self.page_height)
        table_height = table._height
        table.drawOn(c, 2*cm, y_start - 1*cm - table_height)
        
        return y_start - 1*cm - table_height - 0.5*cm
    
    def _draw_attendance_info(self, c: canvas.Canvas, breakdown: SalaryBreakdown, y_start: float):
        """Draw attendance information"""
        logger.debug(f"Drawing attendance info: Business days={breakdown.business_days}, Unpaid={breakdown.unpaid_days}")
        
        c.setFont("Helvetica-Bold", 14)
        c.drawString(2*cm, y_start, "ATTENDANCE INFORMATION")
        
        c.setFont("Helvetica", 10)
        y = y_start - 0.8*cm
        
        info = [
            ("Total Business Days:", str(breakdown.business_days)),
            ("Unpaid Days:", str(breakdown.unpaid_days)),
            ("Days Worked:", str(breakdown.business_days - breakdown.unpaid_days)),
        ]
        
        for label, value in info:
            c.setFont("Helvetica-Bold", 10)
            c.drawString(2*cm, y, label)
            c.setFont("Helvetica", 10)
            c.drawString(6*cm, y, value)
            y -= 0.6*cm
        
        return y - 0.5*cm
    
    def _draw_footer(self, c: canvas.Canvas):
        """Draw PDF footer"""
        c.setFont("Helvetica-Oblique", 8)
        c.setFillColor(colors.grey)
        c.drawString(2*cm, 2*cm, "This document is confidential and for the recipient only.")
        c.drawString(2*cm, 1.6*cm, f"Generated on {datetime.now().strftime('%Y-%m-%d at %H:%M:%S')}")
    
    def _create_pdf_content(
        self,
        filepath: Path,
        user: User,
        period: PayrollPeriod,
        breakdown: SalaryBreakdown,
        currency: str
    ):
        """Create PDF content using ReportLab"""
        logger.debug(f"Creating PDF content for {user.full_name}")
        
        try:
            c = canvas.Canvas(str(filepath), pagesize=A4)
            
            self._draw_header(c, user, period)
            
            y_position = self.page_height - 5.5*cm
            y_position = self._draw_employee_details(c, user, y_position)
            
            y_position = self._draw_salary_table(c, breakdown, currency, y_position)

            y_position = self._draw_attendance_info(c, breakdown, y_position)

            self._draw_footer(c)

            c.save()
            logger.debug(f"PDF content created successfully: {filepath}")
            
        except Exception as e:
            raise PDFGenerationError(
                message=f"Failed to create PDF content",
                user=user,
                period=period,
                original_exception=e
            )
    
    def _protect_pdf_with_password(self, input_path: Path, output_path: Path, password: str):
        """Protect PDF with password using qpdf"""
        logger.debug(f"Protecting PDF with password: {input_path} -> {output_path}")
        
        try:
            result = subprocess.run([
                'qpdf',
                '--encrypt', password, password, '256',
                '--', str(input_path), str(output_path)
            ], check=True, capture_output=True, text=True)
            
            logger.debug(f"PDF protected successfully")
            
        except subprocess.CalledProcessError as e:
            raise PDFGenerationError(
                message=f"Failed to protect PDF with qpdf: {e.stderr}",
                original_exception=e
            )
        except FileNotFoundError:
            raise PDFGenerationError(
                message="qpdf not found. Please install qpdf: apt-get install qpdf"
            )
    
    def _get_currency(self, user: User) -> str:
        """Get currency for user's compensation"""
        try:
            comp = Compensation.objects.get(user=user)
            currency = comp.currency
            logger.debug(f"Currency for {user.full_name}: {currency}")
            return currency
        except Compensation.DoesNotExist:
            logger.warning(f"No compensation found for {user.full_name}, using default RON")
            return "RON"
    
    def generate_pdf(
        self,
        user: User,
        period: PayrollPeriod,
        password: Optional[str] = None
    ) -> Path:
        """Generate password-protected PDF payslip for employee"""
        logger.info(f"Starting PDF generation for {user.full_name} (ID: {user.id}), period {period.label}")
        
        try:
            breakdown = self.calculator.calculate(user, period)
            logger.debug(f"Salary calculated: Net={breakdown.net_total}")
        except Exception as e:
            raise PDFGenerationError(
                message=f"Failed to calculate salary for {user.full_name}",
                user=user,
                period=period,
                original_exception=e
            )

        currency = self._get_currency(user)
        
        # Use CNP as password if not provided
        if password is None:
            password = user.cnp
            logger.debug(f"Using CNP as password for {user.full_name}")

        temp_filename = self._generate_filename(user, period, temp=True)
        final_filename = self._generate_filename(user, period, temp=False)
        
        temp_filepath = self.pdf_dir / temp_filename
        final_filepath = self.pdf_dir / final_filename
        
        try:
            self._create_pdf_content(temp_filepath, user, period, breakdown, currency)

            self._protect_pdf_with_password(temp_filepath, final_filepath, password)

            temp_filepath.unlink()
            logger.debug(f"Temporary file removed: {temp_filepath}")
            
            logger.info(f"PDF generated successfully: {final_filepath}")
            return final_filepath
            
        except PDFGenerationError:
            raise
        except Exception as e:
            if temp_filepath.exists():
                temp_filepath.unlink()
                logger.debug(f"Cleanup: removed temporary file {temp_filepath}")
            if final_filepath.exists():
                final_filepath.unlink()
                logger.debug(f"Cleanup: removed final file {final_filepath}")
            
            raise PDFGenerationError(
                message=f"Failed to generate PDF",
                user=user,
                period=period,
                original_exception=e
            )
    
    def generate_pdfs_for_team(
        self,
        manager: User,
        period: PayrollPeriod,
        employees: Optional[List[User]] = None
    ) -> List[Dict]:
        """Generate PDFs for multiple employees"""
        logger.info(f"Starting PDF generation for team of {manager.full_name} (ID: {manager.id})")
        
        if not manager.is_manager:
            raise PDFGenerationError(
                message=f"User {manager.full_name} is not a manager",
                manager=manager,
                period=period
            )
        
        if employees is None:
            employees = list(manager.direct_reports.filter(is_active=True))
        
        logger.info(f"Processing {len(employees)} employees")
        
        results = []
        success_count = 0
        failed_users = []
        
        for employee in employees:
            try:
                filepath = self.generate_pdf(employee, period)
                results.append({
                    'user': employee,
                    'filepath': filepath,
                    'error': None
                })
                success_count += 1
            except PDFGenerationError as e:
                logger.warning(f"Failed to generate PDF for {employee.full_name}: {e.message}")
                results.append({
                    'user': employee,
                    'filepath': None,
                    'error': str(e)
                })
                failed_users.append(employee.full_name)
        
        if failed_users:
            logger.warning(f"Failed to generate PDFs for {len(failed_users)} employees: {', '.join(failed_users)}")
        
        logger.info(f"PDF generation complete: {success_count} successful, {len(failed_users)} failed")
        
        return results


__all__ = [
    'PDFGenerator',
    'PDFGenerationError',
]