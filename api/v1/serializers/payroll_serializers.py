from rest_framework import serializers
from apps.payroll.models import PayrollPeriod, Compensation, Bonus, Payslip
from .base_serializers import (
    BaseModelSerializer,
    ManagerManagedSerializer,
)


class PayrollPeriodSerializer(BaseModelSerializer):
    """
    Payroll period serializer.
    
    Permissions:
    - Regular users: Can view
    - Managers: Can create/update periods
    - Top managers: Can create/update any period
    
    Note: Period locking is handled at the view level
    """
    label = serializers.ReadOnlyField()
    locked_by_name = serializers.CharField(source='locked_by.full_name',read_only=True,allow_null=True)
    
    class Meta:
        model = PayrollPeriod
        fields = [
            'id',
            'year',
            'month',
            'label',
            'start_date',
            'end_date',
            'is_locked',
            'locked_at',
            'locked_by',
            'locked_by_name',
        ]
        read_only_fields = [
            'id',
            'label',
            'locked_at',
            'locked_by',
            'locked_by_name',
            'is_locked',
        ]
    
    def validate(self, attrs):
        attrs = super().validate(attrs)
        
        start_date = attrs.get('start_date')
        end_date = attrs.get('end_date')
        
        if start_date and end_date and start_date > end_date:
            raise serializers.ValidationError({
                'end_date': 'End date must be after start date'
            })
        return attrs


class CompensationSerializer(ManagerManagedSerializer):
    """
    Permissions:
    - Regular users: Can VIEW their own compensation
    - Regular managers: Can CREATE/UPDATE compensation for direct reports
    - Top managers: Can CREATE/UPDATE any compensation
    """
    full_name = serializers.CharField(source='user.full_name',read_only=True )
    
    class Meta:
        model = Compensation
        fields = [
            'id',
            'user',
            'full_name',
            'amount',
            'currency',
        ]
        read_only_fields = ['id', 'full_name']
    
    def _get_target_user(self, instance):
        return instance.user if instance else None
    
    def validate_user(self, value):
        if not self.instance: 
            if Compensation.objects.filter(user=value).exists():
                raise serializers.ValidationError(
                    f'User {value.full_name} already has a compensation record'
                )
        return value
    
    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError('Compensation must be greater than 0')
        return value


class BonusSerializer(ManagerManagedSerializer):
    """
    Permissions (enforced by ManagerManagedSerializer):
    - Regular users: Can VIEW their own bonuses
    - Regular managers: Can CREATE/UPDATE bonuses for direct reports
    - Top managers: Can CREATE/UPDATE any bonus
    
    - Multiple bonuses per user per period allowed
    """
    full_name = serializers.CharField(source='user.full_name',read_only=True )
    period_label = serializers.CharField(source='period.label',read_only=True)
    
    class Meta:
        model = Bonus
        fields = [
            'id',
            'user',
            'full_name',
            'period',
            'period_label',
            'description',
            'amount',
        ]
        read_only_fields = ['id', 'full_name', 'period_label']
    
    def _get_target_user(self, instance):
        return instance.user if instance else None
    
    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError('Bonus must be greater than 0')
        return value
    
    def validate(self, attrs):
        attrs = super().validate(attrs)
        period = attrs.get('period') or (self.instance.period if self.instance else None)
        if period and period.is_locked:
            raise serializers.ValidationError({
                'period': f'Cannot create or modify bonus for locked period {period.label}'
            })
        return attrs


