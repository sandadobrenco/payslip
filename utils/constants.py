from decimal import Decimal, ROUND_HALF_UP

# Date and time
STANDARD_WORK_HOURS_PER_DAY = 8.0
STANDARD_WORK_DAYS_PER_WEEK = 5
DEFAULT_VACATION_DAYS_PER_YEAR = 21

# Payroll
DEFAULT_CURRENCY = 'RON'
MAX_SALARY_DIGITS = 12
SALARY_DECIMAL_PLACES = 2
MONEY_ROUNDING = ROUND_HALF_UP
MONEY_QUANT = Decimal("1").scaleb(-SALARY_DECIMAL_PLACES)

# Validation limits
MIN_YEAR = 2000
MAX_YEAR = 2100
CNP_LENGTH = 13

# File formats
REPORT_FORMAT_CSV = 'csv'
REPORT_FORMAT_PDF = 'pdf'

# Email settings
EMAIL_SUBJECT_MANAGER_REPORT = "Salary Report - {period}"
EMAIL_SUBJECT_EMPLOYEE_PAYSLIP = "Your Payslip for {period}"
MAX_EMAIL_RETRY_ATTEMPTS = 3

# Archive settings
ARCHIVE_RETENTION_DAYS = 365 * 2 

# Report types
MANAGER_REPORT_FILENAME = "salary_report_{period}_{manager_id}.csv"
EMPLOYEE_PAYSLIP_FILENAME = "payslip_{period}_{user_id}.pdf"

# Email templates
TPL_MANAGER_CSV = "email/manager_report_email.txt"
TPL_EMPLOYEE_PDF = "email/payslip_email.txt"