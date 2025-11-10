"""
Serializers for the API v1
"""
from .base_serializers import (
    BaseModelSerializer,
    ManagerManagedSerializer,
)
from .user_serializers import UserSerializer
from .payroll_serializers import (
    PayrollPeriodSerializer,
    CompensationSerializer,
    BonusSerializer
)
from .attendance_serializers import (
    AttendanceRecordSerializer
)
from .report_serializers import (
    GeneratedReportSerializer,
    EmailLogSerializer,
    CreateAggregatedDataSerializer,
    SendAggregatedDataSerializer,
    CreatePdfSerializer,
    SendPdfSerializer,
    EmployeeReportDataSerializer
)

__all__ = [
    'BaseModelSerializer',
    'ManagerManagedSerializer',
    'ReadOnlyForUsersSerializer',
    'UserSerializer',
    'PayrollPeriodSerializer',
    'CompensationSerializer',
    'BonusSerializer',
    'AttendanceRecordSerializer',
    'GeneratedReportSerializer',
    'EmailLogSerializer',
    'CreateAggregatedDataSerializer',
    'SendAggregatedDataSerializer',
    'CreatePdfSerializer',
    'SendPdfSerializer',
    'EmployeeReportDataSerializer',
]