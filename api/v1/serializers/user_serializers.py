from rest_framework import serializers
from apps.accounts.models import User
from .base_serializers import ManagerManagedSerializer
from django.utils.text import slugify

class UserSerializer(ManagerManagedSerializer):
    """Serializer for GET, POST, PUT, PATCH operations
    
    Business rules:
    - Only managers (is_manager=True) can create users
    - When a manager creates a user, they automatically become that user's manager
    - Top Manager (is_manager = True and manager=None) can update any user from list
    - Regular managers can only update their direct reports
    - Full name is computed from first_name + last_name
    
    """
    full_name = serializers.ReadOnlyField()
    manager_name = serializers.CharField(source='manager.full_name', read_only=True, allow_null=True)
    top_manager = serializers.SerializerMethodField(read_only=True)
    
    password = serializers.CharField(write_only=True, required=False, min_length=8)
    class Meta:
        model = User
        fields = [
            'id',
            'first_name',
            'last_name',
            'full_name',
            'cnp',
            'email',
            'is_manager',
            'manager',
            'manager_name',
            'top_manager',
            'is_active',
            "password",
        ]
        read_only_fields = ['id', 'full_name', 'manager_name', 'top_manager']
        extra_kwargs = {
            'cnp': {'write_only': True},
            'manager': {'required': False, 'allow_null': True},
        }
    
    def get_top_manager(self, obj):
        return self.is_top_manager(obj)
    
    def _validate_assigned_manager(self, mgr):
        if mgr and not getattr(mgr, "is_manager", False):
            raise serializers.ValidationError({'manager': 'Assigned manager must have is_manager=True'})
    
    def create(self, validated_data):
        request_user = self.get_request_user()
        
        password = validated_data.pop('password', None)
        
        if not validated_data.get("username"):
           base = (validated_data.get("email") or "").split("@")[0] or "user"
           cand = slugify(base) or "user"
           i, username = 1, cand
           while User.objects.filter(username=username).exists():
               i, username = i+1, f"{cand}{i}"
           validated_data["username"] = username
           
        if self.is_top_manager(request_user):
            if 'manager' in validated_data and validated_data['manager'] is not None:
                self._validate_assigned_manager(validated_data['manager'])
            else:
                validated_data['manager'] = request_user
        else:
            validated_data['manager'] = request_user
        
        user = super().create(validated_data)
        
        if password:
            user.set_password(password)
            user.save()
            
        return user
    
    
    def update(self, instance, validated_data):
        
        password = validated_data.pop('password', None)
        
        request_user = self.get_request_user()
        if self.is_top_manager(request_user):
            if 'manager' in validated_data:
                self._validate_assigned_manager(validated_data.get('manager'))
        else:
            validated_data.pop('manager', None)
        
        user = super().update(instance, validated_data)
        
        if password:
            user.set_password(password)
            user.save()
            
        return user