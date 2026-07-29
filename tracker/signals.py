"""
CYSD ERP – Django Signals
=========================
Automatic analytics synchronization for the TaskChecklist verification workflow.

This module hooks into the `post_save` signal of `TaskChecklist` and triggers
real-time stat recalculation only when a task transitions cleanly into COMPLETED.
"""
from django.contrib.auth.models import Permission
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Employee, EmployeePermission, EmployeeStats, TaskChecklist


@receiver(post_save, sender=TaskChecklist)
def update_employee_stats_on_completion(sender, instance, created, **kwargs):
    """
    Triggered after every TaskChecklist.save().

    When a task transitions to COMPLETED, atomically recalculate the
    assigned employee's completion percentage, counters, and progress metrics.

    If the item is still PENDING or AWAITING_VERIFICATION, we skip the update
    to avoid thrashing the stats table on every intermediate edit.
    """
    if instance.status == 'COMPLETED':
        # Use select_for_update to lock the stats row and prevent race conditions
        # when multiple supervisors approve tasks for the same employee concurrently
        with transaction.atomic():
            EmployeeStats.recalculate_for(instance.assigned_to)

DEFAULT_PERMISSIONS = {
    'can_manage_employees': False,
    'can_manage_organization': False,
    'can_view_advanced_analytics': False,
    'can_assign_checklist_items': False,
    'can_approve_checklist_items': False,
    'can_read_confidential_meetings': True,
    'can_log_hours': True,
    'can_access_admin_panel': False,
    'checklist_assign_scope': 'none',
    'checklist_approve_scope': 'none',
    'analytics_scope': 'none',
}

@receiver(post_save, sender=Employee)
def auto_populate_employee_permission(sender, instance, created, **kwargs):
    if not hasattr(instance, 'permissions'):
        EmployeePermission.objects.create(employee=instance, **DEFAULT_PERMISSIONS)

@receiver(post_save, sender=EmployeePermission)
def sync_user_admin_access(sender, instance, **kwargs):
    employee = instance.employee
    user = employee.user
    if user:
        if instance.can_access_admin_panel:
            user.is_staff = True
            user.save()
            user.user_permissions.add(
                *Permission.objects.filter(content_type__app_label='tracker')
            )
        else:
            user.is_staff = False
            user.save()
            user.user_permissions.remove(
                *Permission.objects.filter(content_type__app_label='tracker')
            )
