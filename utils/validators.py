from django.core.validators import (
    MinValueValidator, 
    MaxValueValidator, 
    RegexValidator
)
from decimal import Decimal
from utils.constants import MIN_YEAR, MAX_YEAR

year_validator = [MinValueValidator(MIN_YEAR),  MaxValueValidator(MAX_YEAR)]

month_validator = [MinValueValidator(1), MaxValueValidator(12)]

day_validator = [MinValueValidator(0), MaxValueValidator(31)]
day_extended_validator = [MinValueValidator(-365), MaxValueValidator(365)]

cnp_validator = RegexValidator(r'^\d{13}$','CNP must have exactly 13 digits.')
currency_validator = RegexValidator(r'^[A-Z]{3}$','Currency must be a 3 letters  (e.g., RON, EUR, USD).')

positive_decimal_validator = [MinValueValidator(Decimal('0'))]
day_hours_validator = [MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('12.00'))]
month_hours_validator = [MinValueValidator(Decimal('0'))]
