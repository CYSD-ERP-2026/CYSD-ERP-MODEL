from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import EmployeeViewSet, MeetingViewSet, TaskChecklistViewSet, TaskViewSet

# Setup router
router = DefaultRouter()
router.register(r'employees', EmployeeViewSet, basename='employee')
router.register(r'meetings', MeetingViewSet, basename='meeting')
router.register(r'tasks', TaskViewSet, basename='task')
router.register(r'checklists', TaskChecklistViewSet, basename='checklist')

urlpatterns = [
    # JWT Auth
    path('auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # API endpoints
    path('', include(router.urls)),
]
