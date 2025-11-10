from rest_framework import serializers

class ManagerUtilsMixin:
    """
    Utility methods for manager-related operations.
    """
    @staticmethod
    def is_top_manager(user):
        """
        Check if a user is a top manager(manager=None)
        Args:
            user: User instance or None
        Returns:
            bool: True if user is a top manager, False otherwise
        """
        if not user:
            return False
        return getattr(user, 'is_manager', False) and user.manager is None
    
    @staticmethod
    def is_manager(user):
        """
        Check if a user is any type of manager.
        Args:
            user: User instance or None
        Returns:
            bool: True if user is a manager
        """
        if not user:
            return False
        return getattr(user, 'is_manager', False)
    
    @staticmethod
    def get_user_from_instance(instance):
        """
        Extract a User from various instance types.
        Args:
            instance: Model instance
        Returns:
            User instance or None
        """
        if not instance:
            return None
        
        if hasattr(instance, 'is_manager'):
            return instance
        
        if hasattr(instance, 'user'):
            return instance.user
        return None
    
    @staticmethod
    def is_direct_report(manager, user):
        """
        Check if user is a direct report of manager.
        Args:
            manager: User instance
            user: User instance
        Returns:
            bool: True if employee reports directly to manager
        """
        if not manager or not user:
            return False
        return getattr(user, 'manager_id', None) == manager.id


class RequestContextMixin:    
    def get_request(self):
        """Get the request object from serializer context."""
        return self.context.get('request')
    
    def get_request_user(self):
        """
        Get the authenticated user from request context.
        Returns:
            User instance or None
        """
        request = self.get_request()
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            return request.user
        return None
    
    def is_request_user_top_manager(self):
        """
        Check if the requesting user is a top manager.
        Returns:
            bool: True if requesting user is a top manager
        """
        user = self.get_request_user()
        return ManagerUtilsMixin.is_top_manager(user)
    
    def is_request_user_manager(self):
        """
        Check if the requesting user is a manager (any type).
        Returns:
            bool: True if requesting user is a manager
        """
        user = self.get_request_user()
        return ManagerUtilsMixin.is_manager(user)


class ManagerPermissionMixin(ManagerUtilsMixin, RequestContextMixin):
    """
    Manager permission checking.
    """
    def can_manager_access_user(self, target_user, manager=None):
        """
        Check if a manager can access or modify a specific user's data
        Rules:
        - Top manager: can access anyone
        - Regular manager: can access direct reports only
        - Regular user: cannot access others
        Args:
            target_user: The user whose data is being accessed
            manager: The manager checking permission
        Returns:
            bool: True if manager can access target_user's data
        """
        if manager is None:
            manager = self.get_request_user()
        
        if not manager or not target_user:
            return False
        
        if manager.id == target_user.id:
            return True
        
        if self.is_top_manager(manager):
            return True
        
        if self.is_manager(manager):
            return self.is_direct_report(manager, target_user)
        
        return False
    
    def require_manager_permission(self, target_user, manager=None, error_message=None):
        """
        Validate that manager has permission to access target_user
        Args:
            target_user: The user whose data is being accessed
            manager: The manager
        Raises:
            ValidationError: If manager doesn't have permission
        """
        if not self.can_manager_access_user(target_user, manager):
            if error_message is None:
                error_message = (
                    'You can only access your direct reports'
                )
            raise serializers.ValidationError({'detail': error_message})
    
class ManagerScopeValidationMixin(ManagerPermissionMixin):
    """
    Validates manager scope on update operations.
    
    Use this for models where:
    - Top managers can update anything
    - Regular managers can only update their team's data
    - Regular users cannot update
    """
    
    def _get_target_user(self, instance):
        return self.get_user_from_instance(instance)
    
    def validate(self, attrs):
        """
        Validate manager permissions on update operations.
        """
        attrs = super().validate(attrs)
        
        if self.instance:
            request_user = self.get_request_user()
            target_user = self._get_target_user(self.instance)
            
            if target_user:
                self.require_manager_permission(target_user, request_user)
        
        return attrs


class BaseModelSerializer(serializers.ModelSerializer, ManagerUtilsMixin, RequestContextMixin):
    """
    Base serializer used unversally by almost all serializers
    Provides access to manager utility methods without any validation.
    """
    def get_fields(self):
        fields = super().get_fields()
        ro = getattr(getattr(self, 'Meta', None), 'read_only_fields', None)
        if ro == '__all__':
            for f in fields.values():
                f.read_only = True
        return fields

class ManagerManagedSerializer(ManagerScopeValidationMixin, BaseModelSerializer):
    """
    Serializer for resources managed by managers.
    Automatically validates that:
    - Only managers can modify
    - Top managers can modify anything
    - Regular managers can only modify their team's resources
    """
    def _get_target_user(self, instance):
        if instance is not None and hasattr(instance, 'user'):
            return instance.user
        return super()._get_target_user(instance)
    
    def _get_target_user_from_attrs(self, attrs):
        return attrs.get('user')
    
    def validate(self, attrs):
        request_user = self.get_request_user()
        if not self.is_manager(request_user):
            raise serializers.ValidationError({'detail': 'Only managers can create or modify this resource'})
        if self.instance:
            target_user = self._get_target_user(self.instance)
        else:
            target_user = self._get_target_user_from_attrs(attrs)  
        if target_user is not None:
            self.require_manager_permission(target_user, request_user)
        return attrs


class ReadOnlyForUsersSerializer(BaseModelSerializer):
    """
    Serializer that is read-only for regular users.
    """
    def get_fields(self):
        fields = super().get_fields()
        try:
            if not self.is_request_user_manager():
                for f in fields.values():
                    f.read_only = True
        except Exception:
            pass
        return fields