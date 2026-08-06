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
    'can_assign_checklist_items': False,
    'can_approve_checklist_items': False,
    'can_read_confidential_meetings': True,
    'can_access_admin_panel': False,
    'can_self_assign_tasks': True,
    'can_view_employee_analytics': False,
    'checklist_assign_scope': 'none',
    'checklist_approve_scope': 'none',
    'employee_analytics_scope': 'none',
}

@receiver(post_save, sender=Employee)
def auto_populate_employee_permission(sender, instance, created, **kwargs):
    """
    Create a default EmployeePermission row whenever a new Employee is saved
    and one does not already exist.

    BUG FIX: hasattr(instance, 'permissions') always returns True on a saved
    Employee because Django's ORM reverse OneToOne descriptor returns a
    RelatedObjectDoesNotExist exception lazily — hasattr catches it and returns
    False only on *attribute access*, not on the presence of the descriptor.
    In practice the descriptor IS present even when the row doesn't exist,
    so hasattr was returning True and the permission row was never created.

    Correct approach: use filter().exists() which hits the database properly.
    """
    if not EmployeePermission.objects.filter(employee=instance).exists():
        EmployeePermission.objects.create(employee=instance, **DEFAULT_PERMISSIONS)

@receiver(post_save, sender=EmployeePermission)
def sync_user_admin_access(sender, instance, **kwargs):
    employee = instance.employee
    user = employee.user
    if not user:
        return

    tracker_perms = Permission.objects.filter(content_type__app_label='tracker')
    if instance.can_access_admin_panel:
        user.is_staff = True
        user.save(update_fields=['is_staff'])
        user.user_permissions.add(*tracker_perms)
    else:
        user.is_staff = False
        user.save(update_fields=['is_staff'])
        user.user_permissions.remove(*tracker_perms)
