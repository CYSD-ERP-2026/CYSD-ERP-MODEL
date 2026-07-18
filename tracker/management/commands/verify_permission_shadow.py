"""
Management command: verify_permission_shadow
=============================================

Iterates every Employee in the database and asserts that the old role-based
authorization decision matches the new EmployeePermission-based decision for
all authorization gates identified in the audit.

Usage::

    py manage.py verify_permission_shadow

Exit code 0  = zero mismatches (safe to proceed to Phase 3)
Exit code 1  = at least one mismatch detected
"""
from django.core.management.base import BaseCommand

from tracker.models import Employee

# Maps check name → (compute_old_fn, compute_new_fn)
# Each function takes (employee, perms) and returns a comparable value.


def _old_can_create_checklist(emp, _perms):
    return emp.role in ('founder', 'hr', 'supervisor')


def _new_can_create_checklist(_emp, perms):
    return bool(perms and perms.can_assign_checklist_items)


def _old_checklist_assign_scope(emp, _perms):
    if emp.role in ('founder', 'hr'):
        return 'all'
    if emp.role == 'supervisor':
        return 'own_team'
    return 'none'


def _new_checklist_assign_scope(_emp, perms):
    if perms and perms.can_assign_checklist_items:
        return perms.checklist_assign_scope
    return 'none'


def _old_can_approve_checklist(emp, _perms):
    return emp.role in ('founder', 'hr', 'supervisor')


def _new_can_approve_checklist(_emp, perms):
    return bool(perms and perms.can_approve_checklist_items)


def _old_checklist_approve_scope(emp, _perms):
    if emp.role in ('founder', 'hr'):
        return 'all'
    if emp.role == 'supervisor':
        return 'own_team'
    return 'none'


def _new_checklist_approve_scope(_emp, perms):
    if perms and perms.can_approve_checklist_items:
        return perms.checklist_approve_scope
    return 'none'


def _old_analytics_scope(emp, _perms):
    if emp.role in ('founder', 'hr'):
        return 'all'
    if emp.role == 'supervisor':
        return 'own_team'
    return 'self'


def _new_analytics_scope(_emp, perms):
    if perms and perms.can_view_advanced_analytics:
        if perms.analytics_scope == 'all':
            return 'all'
        if perms.analytics_scope == 'own_team':
            return 'own_team'
    return 'self'


def _old_confidential_meetings_masked(emp, _perms):
    """True means content IS masked (i.e. the employee cannot see confidential data)."""
    return emp.role == 'hr'


def _new_confidential_meetings_masked(_emp, perms):
    return not perms.can_read_confidential_meetings if perms else True


def _old_setup_org_access(emp, _perms):
    return emp.role in ('founder', 'hr')


def _new_setup_org_access(_emp, perms):
    return bool(perms and perms.can_manage_organization)


def _old_admin_panel_access(emp, _perms):
    return emp.role in ('founder', 'hr', 'supervisor')


def _new_admin_panel_access(_emp, perms):
    return bool(perms and perms.can_access_admin_panel)


CHECKS = [
    ('can_create_checklist',       _old_can_create_checklist,      _new_can_create_checklist),
    ('checklist_assign_scope',     _old_checklist_assign_scope,    _new_checklist_assign_scope),
    ('can_approve_checklist',      _old_can_approve_checklist,     _new_can_approve_checklist),
    ('checklist_approve_scope',    _old_checklist_approve_scope,   _new_checklist_approve_scope),
    ('analytics_scope',            _old_analytics_scope,           _new_analytics_scope),
    ('confidential_meetings_mask', _old_confidential_meetings_masked, _new_confidential_meetings_masked),
    ('setup_org_access',           _old_setup_org_access,          _new_setup_org_access),
    ('admin_panel_access',         _old_admin_panel_access,        _new_admin_panel_access),
]


class Command(BaseCommand):
    help = (
        'Verify that the EmployeePermission rows match the old role-based '
        'authorization decisions for every Employee.'
    )

    def handle(self, *args, **options):
        employees = Employee.objects.select_related('permissions').all()
        total = employees.count()
        mismatches = 0
        missing_perms = 0

        self.stdout.write(f'\nVerifying {total} employee(s)...\n')
        self.stdout.write('=' * 80)

        for emp in employees:
            perms = getattr(emp, 'permissions', None)
            if perms is None:
                self.stdout.write(
                    self.style.ERROR(
                        f'  MISSING  emp={emp.pk} name="{emp.name}" role={emp.role} '
                        f'— no EmployeePermission row exists!'
                    )
                )
                missing_perms += 1
                continue

            for check_name, old_fn, new_fn in CHECKS:
                old_val = old_fn(emp, perms)
                new_val = new_fn(emp, perms)
                if old_val != new_val:
                    mismatches += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f'  MISMATCH  emp={emp.pk} name="{emp.name}" '
                            f'role={emp.role} check={check_name} '
                            f'old={old_val} new={new_val}'
                        )
                    )

        self.stdout.write('=' * 80)

        if missing_perms:
            self.stdout.write(
                self.style.ERROR(
                    f'\n{missing_perms} employee(s) have NO EmployeePermission row.'
                )
            )

        if mismatches:
            self.stdout.write(
                self.style.ERROR(
                    f'\n{mismatches} MISMATCH(ES) detected across {total} employee(s).'
                )
            )
            self.stdout.write(
                self.style.ERROR(
                    'DO NOT proceed to Phase 3 until all mismatches are resolved.'
                )
            )
            raise SystemExit(1)
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nPASSED: ZERO mismatches across {total} employee(s) '
                    f'and {len(CHECKS)} checks each. Safe to proceed to Phase 3.'
                )
            )
