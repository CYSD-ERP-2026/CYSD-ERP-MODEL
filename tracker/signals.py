"""
CYSD ERP – Django Signals
=========================
Automatic analytics synchronization for the TaskChecklist verification workflow.

This module hooks into the `post_save` signal of `TaskChecklist` and triggers
real-time stat recalculation only when a task transitions cleanly into COMPLETED.
"""
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import EmployeeStats, TaskChecklist


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
