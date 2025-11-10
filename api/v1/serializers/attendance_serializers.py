from rest_framework import serializers
from decimal import Decimal
from apps.attendance.models import (
    AttendanceRecord,
    AttendanceType
)
from .base_serializers import ManagerManagedSerializer


class AttendanceRecordSerializer(ManagerManagedSerializer):
    """
    Serializer for attendance records
    Permissions:
    - Top managers: can create/update for anyone
    - Regular managers: can create/update for direct reports
    - Regular users: read-only
    """
    full_name = serializers.CharField(source='user.full_name', read_only=True)
    type_display = serializers.CharField(source='get_type_display', read_only=True)
    is_working_day = serializers.BooleanField(read_only=True)
    is_paid_leave = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = AttendanceRecord
        fields = [
            'id',
            'user',
            'full_name',
            'date',
            'type',
            'type_display',
            'hours_worked',
            'is_working_day',
            'is_paid_leave',
        ]
        read_only_fields = ['id']
    
    def _get_target_user(self, instance):
        return instance.user
    
    def validate(self, attrs):
        """
        Validate attendance record data with business rules
        """
        attrs = super().validate(attrs)
        
        attendance_type = attrs.get('type', getattr(self.instance, 'type', None))
        hours_worked = attrs.get('hours_worked', getattr(self.instance, 'hours_worked', None))
        
        if attendance_type in [AttendanceType.VACATION, AttendanceType.UNPAID_LEAVE]:
            if hours_worked and hours_worked != Decimal('0.00'):
                raise serializers.ValidationError({
                    'hours_worked': f'{attendance_type} must have 0 hours worked.'
                })
            attrs['hours_worked'] = Decimal('0.00')
        if attendance_type == AttendanceType.WORKED:
            if not hours_worked or hours_worked <= 0:
                raise serializers.ValidationError({
                    'hours_worked': 'Worked days must have hours greater than 0'
                })
        if attendance_type == AttendanceType.PUBLIC_HOLIDAY:
            if hours_worked and hours_worked != Decimal('0.00'):
                raise serializers.ValidationError({'hours_worked': 'Public holiday must have 0 hours worked.'})
            attrs['hours_worked'] = Decimal('0.00')
        return attrs
    
    def validate_user(self, value):
        """
        Validate that managers can only create records for their team
        """
        request_user = self.get_request_user()
        if not self.instance:
            self.require_manager_permission(
                value, 
                request_user,
                error_message='You can only create attendance records for your direct reports'
            )
        return value

