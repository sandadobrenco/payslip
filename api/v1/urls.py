from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import(
    UserViewSet,
    PayrollPeriodViewSet,
    CompensationViewSet,
    BonusViewSet,
    AttendanceRecordViewSet,
    CreateAggregatedEmployeeData,
    SendAggregatedEmployeeData,
    CreatePdfForEmployees,
    SendPdfToEmployees,)
router = DefaultRouter()
router.register(r'users', UserViewSet, basename='users')
router.register(r'periods', PayrollPeriodViewSet, basename='periods')
router.register(r'compensations', CompensationViewSet, basename='compensations')
router.register(r'bonuses', BonusViewSet, basename='bonuses')
router.register(r'attendance', AttendanceRecordViewSet, basename='attendance')

urlpatterns = [
    path("", include(router.urls)), 
    path('reports/create-csv/', CreateAggregatedEmployeeData.as_view(), name='reports-create-csv'),
    path('reports/send-csv/',   SendAggregatedEmployeeData.as_view(),  name='reports-send-csv'),
    path('reports/create-pdf/', CreatePdfForEmployees.as_view(),       name='reports-create-pdf'),
    path('reports/send-pdf/',   SendPdfToEmployees.as_view(),          name='reports-send-pdf'),
]