from rest_framework import serializers
from apps.reports.models import (
    GeneratedReport,
    EmailLog,
    ReportType)
from apps.payroll.models import PayrollPeriod
from .base_serializers import BaseModelSerializer, ReadOnlyForUsersSerializer


class GeneratedReportSerializer(ReadOnlyForUsersSerializer):
    """
    Serializer for generated reports
    """
    file = serializers.SerializerMethodField(read_only=True)
    period_label = serializers.CharField(source='period.label', read_only=True)
    manager_full_name = serializers.CharField(source='manager.full_name', read_only=True, allow_null=True)
    full_name = serializers.CharField(source='user.full_name', read_only=True, allow_null=True)
    is_sent = serializers.BooleanField(read_only=True)
    is_archived = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = GeneratedReport
        fields = [
            'id',
            'type',
            'period',
            'period_label',
            'manager',
            'manager_full_name',
            'user',
            'full_name',
            'file',
            'file_format',
            'sent_at',
            'archived_at',
            'is_sent',
            'is_archived',
        ]
        read_only_fields = [
            'id',
            'type',
            'period',
            'manager',
            'user',
            'file',
            'file_format',
            'sent_at',
            'archived_at',
        ]
    def get_file(self, obj):
        return obj.file.url if getattr(obj, "is_sent", False) and obj.file else None

class EmailLogSerializer(BaseModelSerializer):
    """
    Serializer for email logs
    Tracks email sending status
    """
    report_type = serializers.CharField(source='report.type', read_only=True)
    
    class Meta:
        model = EmailLog
        fields = [
            'id',
            'report',
            'report_type',
            'to_email',
            'subject',
            'status',
            'error_message',
            'sent_at',
            'attempts',
        ]
        read_only_fields = [
            'id',
            'status',
            'error_message',
            'sent_at',
            'attempts',
        ]


class EmployeeReportDataSerializer(serializers.Serializer):
    """
    Serializer for employee data to be included in reports
    Used for user's validation when creating reports
    """
    user_id = serializers.IntegerField()
    full_name = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)
    
    def validate_user_id(self, value):
        """Validate that the user exists and requester has permission"""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        try:
            user = User.objects.get(id=value)
        except User.DoesNotExist:
            raise serializers.ValidationError(f'User with id {value} does not exist.')
        
        request_user = self.context.get('request').user if self.context.get('request') else None
        
        if not request_user:
            raise serializers.ValidationError('Request context is required.')
        
        if not self.context.get('skip_permission_check', False):
            from .base_serializers import ManagerUtilsMixin
            
            if not ManagerUtilsMixin.is_top_manager(request_user):
                if not (ManagerUtilsMixin.is_manager(request_user) and 
                       ManagerUtilsMixin.is_direct_report(request_user, user)):
                    raise serializers.ValidationError(
                        f'You do not have permission to include user {value} in reports.'
                    )
        
        return value


class CreateAggregatedDataSerializer(BaseModelSerializer):
    """
    Serializer for creating aggregated CSV reports (manager reports)
    """
    period = serializers.PrimaryKeyRelatedField(queryset=PayrollPeriod.objects.all())
    user_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        help_text="List of user IDs to include. If not specifically indicated, all direct reports are included"
    )
    
    class Meta:
        model = GeneratedReport
        fields = ['period', 'user_ids']
    
    def validate_period(self, value):
        """Validate that the period exists and is accessible"""
        if not value:
            raise serializers.ValidationError('Period is required')
        return value
    
    def validate_user_ids(self, value):
        """Validate that all user IDs are valid and accessible"""
        if not value:
            return value
        
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        request_user = self.context.get('request').user if self.context.get('request') else None
        
        if not request_user:
            raise serializers.ValidationError('Request context is required')
        
        from .base_serializers import ManagerUtilsMixin
        
        for user_id in value:
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                raise serializers.ValidationError(f'User with id {user_id} does not exist')
            
            if not ManagerUtilsMixin.is_top_manager(request_user):
                if not (ManagerUtilsMixin.is_manager(request_user) and 
                       ManagerUtilsMixin.is_direct_report(request_user, user)):
                    raise serializers.ValidationError(
                        f'You do not have permission to include user {user_id} in reports'
                    )
        
        return value
    
    def validate(self, attrs):
        attrs = super().validate(attrs)
        
        request_user = self.context.get('request').user if self.context.get('request') else None
        
        if not request_user or not request_user.is_manager:
            raise serializers.ValidationError({
                'detail': 'Only managers can create aggregated reports.'
            })
        
        return attrs


class SendAggregatedDataSerializer(serializers.Serializer):
    """
    Serializer for sending aggregated CSV reports via email.
    """
    period = serializers.PrimaryKeyRelatedField(queryset=PayrollPeriod.objects.all())
    include_indirect = serializers.BooleanField(required=False, default=True)
    email = serializers.EmailField(
        required=False,
        help_text="Email to 'send to'. If not provided, uses manager's email"
    )
    subject = serializers.CharField(
        max_length=200,
        required=False,
        help_text="Email subject. If not provided, uses default."
    )

class CreatePdfSerializer(BaseModelSerializer):
    """
    Serializer for creating individual PDF reports for employees.
    """
    period = serializers.PrimaryKeyRelatedField(queryset=PayrollPeriod.objects.all())
    user_id = serializers.IntegerField(help_text="User ID for whom to generate the PDF report")
    
    class Meta:
        model = GeneratedReport
        fields = ['period', 'user_id']
    
    def validate_period(self, value):
        """Validate that the period exists"""
        if not value:
            raise serializers.ValidationError('Period is required.')
        return value
    
    def validate_user_id(self, value):
        """Validate that the user exists and requester has permission"""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        try:
            user = User.objects.get(id=value)
        except User.DoesNotExist:
            raise serializers.ValidationError(f'User with id {value} does not exist')
        
        request_user = self.context.get('request').user if self.context.get('request') else None
        
        if not request_user:
            raise serializers.ValidationError('Request context is required')
        
        from .base_serializers import ManagerUtilsMixin
        
        if not ManagerUtilsMixin.is_top_manager(request_user):
            if not (ManagerUtilsMixin.is_manager(request_user) and 
                   ManagerUtilsMixin.is_direct_report(request_user, user)):
                raise serializers.ValidationError(
                    f'You do not have permission to create reports for user {value}'
                )
        
        return value
    
    def validate(self, attrs):
        attrs = super().validate(attrs)
        
        request_user = self.context.get('request').user if self.context.get('request') else None
        
        if not request_user or not request_user.is_manager:
            raise serializers.ValidationError({
                'detail': 'Only managers can create PDF reports'
            })
        
        return attrs


class SendPdfSerializer(serializers.Serializer):
    """
    Serializer for sending PDF reports via email to employees
    """
    report_id = serializers.IntegerField()
    email = serializers.EmailField(
        required=False,
        help_text="Email to 'send to'. If not provided, uses employee's email"
    )
    subject = serializers.CharField(
        max_length=200,
        required=False,
        help_text="Email subject. If not provided, uses default"
    )
    
    def validate_report_id(self, value):
        """Validate that the report exists and requester has permission"""
        try:
            report = GeneratedReport.objects.get(id=value)
        except GeneratedReport.DoesNotExist:
            raise serializers.ValidationError(f'Report with id {value} does not exist')
        
        if report.type != ReportType.USER_PDF:
            raise serializers.ValidationError('Only PDF user reports can be sent through this endpoint')
        
        request_user = self.context.get('request').user if self.context.get('request') else None
        
        if not request_user:
            raise serializers.ValidationError('Request context is required')
        
        from .base_serializers import ManagerUtilsMixin
        
        if ManagerUtilsMixin.is_top_manager(request_user):
            return value
        
        if ManagerUtilsMixin.is_manager(request_user):
            if report.user and ManagerUtilsMixin.is_direct_report(request_user, report.user):
                return value
        
        raise serializers.ValidationError('You can only send reports for your direct reports')
    
    def validate(self, attrs):
        attrs = super().validate(attrs)
        
        request_user = self.context.get('request').user if self.context.get('request') else None
        
        if not request_user or not request_user.is_manager:
            raise serializers.ValidationError({
                'detail': 'Only managers can send PDF reports'
            })
        return attrs
