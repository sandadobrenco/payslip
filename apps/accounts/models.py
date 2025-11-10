from django.db import models
from utils.validators import cnp_validator
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    """User model with hierarchical manager relationship"""
    first_name = models.CharField(max_length=50, null=False, blank=False)
    last_name = models.CharField(max_length=50, null=False, blank=False)
    cnp = models.CharField(max_length=13, unique=True, null=False, blank=False, validators=[cnp_validator])
    email = models.EmailField(unique=True)
    is_manager = models.BooleanField(default=False)
    manager = models.ForeignKey('self', null=True, blank=True, 
                                on_delete=models.SET_NULL,
                                related_name='direct_reports')
    is_active = models.BooleanField(default=True)
    
    REQUIRED_FIELDS = ['email']
    
    class Meta:
        db_table = 'users'
        indexes = [
            models.Index(fields=['manager']),
            models.Index(fields=['last_name', 'first_name']),
            models.Index(fields=['email']),
        ]
        constraints = [
            #An employee can't be his own manager
            models.CheckConstraint(
                name='employee_not_own_manager',
                check=models.Q(manager__isnull=True) | ~models.Q(pk=models.F('manager')),
            ),
        ]
        ordering = ['last_name', 'first_name']
    
    def __str__(self):
        return f"{self.full_name} <{self.email}>"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    @property
    def has_direct_reports(self) -> bool:
        "True if has at least one subordinate employee "
        return self.direct_reports.filter(is_active=True).exists()
    
    @property
    def able_create_reports(self) -> bool:
        #Permission to create reports for manager
        return self.is_active and self.is_manager
    
    @property
    def is_top_manager(self) -> bool:
        return self.is_manager and self.manager is None
    
    def get_all_subordinates(self, include_indirect=True):
        """
        Get all subordinates of this manager"""
        if not self.is_manager:
            return User.objects.none()
        
        if not include_indirect:
            return self.direct_reports.filter(is_active=True)
        subordinates = set()
        to_process = list(self.direct_reports.filter(is_active=True))
        
        while to_process:
            employee = to_process.pop(0)
            if employee.id not in subordinates:
                subordinates.add(employee.id)
                to_process.extend(
                    employee.direct_reports.filter(is_active=True)
                )
        
        return User.objects.filter(id__in=subordinates)
    

    
    
