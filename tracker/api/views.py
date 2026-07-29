from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from tracker.models import Employee, Meeting, Task, TaskChecklist
from .serializers import EmployeeSerializer, MeetingSerializer, TaskSerializer, TaskChecklistSerializer

class TenantFilteredViewSet(viewsets.ModelViewSet):
    """Base ViewSet that automatically filters querysets by the request's tenant."""
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if hasattr(self.request, 'tenant') and self.request.tenant:
            return self.queryset.filter(enterprise=self.request.tenant)
        return self.queryset.none()

class EmployeeViewSet(TenantFilteredViewSet):
    queryset = Employee.objects.all()
    serializer_class = EmployeeSerializer

class MeetingViewSet(TenantFilteredViewSet):
    queryset = Meeting.objects.all()
    serializer_class = MeetingSerializer

class TaskViewSet(TenantFilteredViewSet):
    queryset = Task.objects.all()
    serializer_class = TaskSerializer

class TaskChecklistViewSet(TenantFilteredViewSet):
    queryset = TaskChecklist.objects.all()
    serializer_class = TaskChecklistSerializer

    @action(detail=True, methods=['post'])
    def mark_completed(self, request, pk=None):
        checklist = self.get_object()
        checklist.status = 'COMPLETED'
        checklist.save()
        return Response({'status': 'Checklist marked as completed'})
