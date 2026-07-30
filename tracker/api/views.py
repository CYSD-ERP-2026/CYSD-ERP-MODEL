import logging

from django.utils import timezone
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from tracker.models import Employee, EmployeeStats, Meeting, Task, TaskChecklist

from .serializers import (
    EmployeeSerializer,
    MeetingSerializer,
    TaskChecklistSerializer,
    TaskSerializer,
)

logger = logging.getLogger(__name__)


class TenantFilteredViewSet(viewsets.ModelViewSet):
    """Base ViewSet that automatically filters querysets by the request's tenant."""
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return self.queryset


class TenantReadOnlyViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Read-only ViewSet that filters by the request's tenant."""
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return self.queryset


class EmployeeViewSet(TenantReadOnlyViewSet):
    """Read-only API for employee records. Write operations are managed via admin/dashboard."""
    queryset = Employee.objects.all()
    serializer_class = EmployeeSerializer


class MeetingViewSet(TenantReadOnlyViewSet):
    """Read-only API for meeting records."""
    queryset = Meeting.objects.all()
    serializer_class = MeetingSerializer


class TaskViewSet(TenantReadOnlyViewSet):
    """Read-only API for task records."""
    queryset = Task.objects.all()
    serializer_class = TaskSerializer


class TaskChecklistViewSet(TenantReadOnlyViewSet):
    """Read-only API for checklist records with a secure mark_completed action."""
    queryset = TaskChecklist.objects.all()
    serializer_class = TaskChecklistSerializer

    @action(detail=True, methods=['post'])
    def mark_completed(self, request, pk=None):
        """
        Mark a checklist item as COMPLETED.

        Requires the caller to have can_approve_checklist_items permission,
        and the item must be in AWAITING_VERIFICATION status.
        Scope checks (own_team vs all) are enforced.
        """
        # Permission check: caller must have approval permissions
        profile = getattr(request.user, 'employee_profile', None)
        perms = getattr(profile, 'permissions', None) if profile else None

        if not perms or not perms.can_approve_checklist_items:
            return Response(
                {'error': 'You do not have permission to approve checklist items.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        checklist = self.get_object()

        # Scope check: own_team supervisors can only approve their reports' items
        if perms.checklist_approve_scope == 'own_team':
            if checklist.assigned_to.supervisor_id != profile.pk:
                return Response(
                    {'error': 'You can only approve items assigned to your direct reports.'},
                    status=status.HTTP_403_FORBIDDEN,
                )

        # Status check: only AWAITING_VERIFICATION items can be completed
        if checklist.status != 'AWAITING_VERIFICATION':
            return Response(
                {'error': 'Only items awaiting verification can be approved.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Use queryset.update() to bypass full_clean() creation validations
        now = timezone.now()
        TaskChecklist.objects.filter(pk=checklist.pk).update(
            status='COMPLETED',
            rejection_feedback='',
            resolved_at=now,
        )

        # Recalculate stats for the assigned employee
        checklist.refresh_from_db()
        EmployeeStats.recalculate_for(checklist.assigned_to)

        return Response({'status': 'Checklist item approved and marked as completed.'})
