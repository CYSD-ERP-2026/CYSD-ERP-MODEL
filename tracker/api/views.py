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


class EmployeeViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Read-only API for employee records.

    Access control (mirrors web dashboard):
      - Callers with ``can_manage_employees`` see all Employee records.
      - Everyone else sees only their own record.
    """

    serializer_class = EmployeeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        profile = getattr(user, 'employee_profile', None)
        perms = getattr(profile, 'permissions', None) if profile else None

        if perms and perms.can_manage_employees:
            return Employee.objects.all()

        # Fall back to own record only
        if profile:
            return Employee.objects.filter(pk=profile.pk)
        return Employee.objects.none()


class MeetingViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Read-only API for meeting records.

    Access control (mirrors web dashboard):
      - All authenticated users can list meetings.
      - Confidential fields (agenda, minutes, action_points) are masked
        unless the caller has ``can_read_confidential_meetings``.
    """

    serializer_class = MeetingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Meeting.objects.all()

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        self._mask_confidential_fields(request, response)
        return response

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        self._mask_confidential_fields(request, response)
        return response

    def _mask_confidential_fields(self, request, response):
        """Mask agenda, minutes, and action_points for callers without
        ``can_read_confidential_meetings`` permission — the same masking
        the web dashboard applies."""
        profile = getattr(request.user, 'employee_profile', None)
        perms = getattr(profile, 'permissions', None) if profile else None

        if perms and perms.can_read_confidential_meetings:
            return  # Full access — nothing to mask

        masked = 'Confidential - Access Restricted'
        confidential_fields = ('agenda', 'minutes', 'action_points')

        data = response.data
        # Paginated results nest the list under 'results'
        items = data.get('results', data) if isinstance(data, dict) else data

        if isinstance(items, list):
            for item in items:
                for field in confidential_fields:
                    if field in item:
                        item[field] = masked
        elif isinstance(items, dict):
            for field in confidential_fields:
                if field in items:
                    items[field] = masked


class TaskViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Read-only API for task records.

    Access control (mirrors ``checklist_supervisor_view`` / dashboard):
      - ``checklist_approve_scope == 'all'``:  all tasks.
      - ``checklist_approve_scope == 'own_team'``:  tasks assigned to
        the caller's direct reports.
      - Everyone else: only their own tasks.
    """

    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        profile = getattr(user, 'employee_profile', None)
        perms = getattr(profile, 'permissions', None) if profile else None

        if perms and perms.can_approve_checklist_items:
            if perms.checklist_approve_scope == 'all':
                return Task.objects.all()
            if perms.checklist_approve_scope == 'own_team':
                subordinate_ids = list(
                    Employee.objects.filter(supervisor=profile)
                    .values_list('id', flat=True)
                )
                return Task.objects.filter(assigned_to__id__in=subordinate_ids)

        # Base role: own tasks only
        if profile:
            return Task.objects.filter(assigned_to=profile)
        return Task.objects.none()


class TaskChecklistViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Read-only API for checklist records with a secure mark_completed action.

    Access control (mirrors ``checklist_supervisor_view``):
      - ``checklist_approve_scope == 'all'``:  all checklist items.
      - ``checklist_approve_scope == 'own_team'``:  items assigned to
        the caller's direct reports.
      - Everyone else: only items assigned to themselves.
    """

    serializer_class = TaskChecklistSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        profile = getattr(user, 'employee_profile', None)
        perms = getattr(profile, 'permissions', None) if profile else None

        if perms and perms.can_approve_checklist_items:
            if perms.checklist_approve_scope == 'all':
                return TaskChecklist.objects.all()
            if perms.checklist_approve_scope == 'own_team':
                subordinate_ids = list(
                    Employee.objects.filter(supervisor=profile)
                    .values_list('id', flat=True)
                )
                return TaskChecklist.objects.filter(
                    assigned_to__id__in=subordinate_ids
                )

        # Base role: own items only
        if profile:
            return TaskChecklist.objects.filter(assigned_to=profile)
        return TaskChecklist.objects.none()

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
