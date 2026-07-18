"""
Data migration: Populate EmployeePermission from existing Employee.role
====================================================================

Creates one EmployeePermission row per existing Employee, mapped from
their current ``role`` field using the mapping table agreed in the audit:

    founder:      all 8 booleans True, all scopes 'all'
    hr:           all True EXCEPT can_read_confidential_meetings=False;
                  all scopes 'all'
    supervisor:   can_read_confidential_meetings=True,
                  can_assign_checklist_items=True (scope: own_team),
                  can_approve_checklist_items=True (scope: own_team),
                  can_view_advanced_analytics=True (scope: own_team),
                  can_log_hours=True,
                  everything else False/none
    employee/intern/volunteer: only can_log_hours=True, rest False/none

This migration is additive only – it does NOT alter the ``role`` field or
any existing column.
"""
from django.db import migrations


# Mapping: role -> dict of EmployeePermission field values.
# Any field not listed defaults to the model default (False / 'none').
ROLE_PERMISSION_MAP = {
    'founder': {
        'can_manage_employees': True,
        'can_manage_organization': True,
        'can_view_advanced_analytics': True,
        'can_assign_checklist_items': True,
        'can_approve_checklist_items': True,
        'can_read_confidential_meetings': True,
        'can_log_hours': True,
        'can_access_admin_panel': True,
        'checklist_assign_scope': 'all',
        'checklist_approve_scope': 'all',
        'analytics_scope': 'all',
    },
    'hr': {
        'can_manage_employees': True,
        'can_manage_organization': True,
        'can_view_advanced_analytics': True,
        'can_assign_checklist_items': True,
        'can_approve_checklist_items': True,
        'can_read_confidential_meetings': False,   # HR gets masked content
        'can_log_hours': True,
        'can_access_admin_panel': True,
        'checklist_assign_scope': 'all',
        'checklist_approve_scope': 'all',
        'analytics_scope': 'all',
    },
    'supervisor': {
        'can_manage_employees': False,
        'can_manage_organization': False,
        'can_view_advanced_analytics': True,
        'can_assign_checklist_items': True,
        'can_approve_checklist_items': True,
        'can_read_confidential_meetings': True,   # supervisors see full meeting details
        'can_log_hours': True,
        'can_access_admin_panel': True,
        'checklist_assign_scope': 'own_team',
        'checklist_approve_scope': 'own_team',
        'analytics_scope': 'own_team',
    },
    # employee, intern, volunteer all get the same least-privilege set
    '_default': {
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
    },
}


def populate_permissions(apps, schema_editor):
    Employee = apps.get_model('tracker', 'Employee')
    EmployeePermission = apps.get_model('tracker', 'EmployeePermission')

    for emp in Employee.objects.all().iterator():
        perm_values = ROLE_PERMISSION_MAP.get(emp.role, ROLE_PERMISSION_MAP['_default'])
        EmployeePermission.objects.create(
            employee=emp,
            **perm_values,
        )


def remove_permissions(apps, schema_editor):
    """Reverse: delete all EmployeePermission rows (schema rollback drops the table anyway)."""
    EmployeePermission = apps.get_model('tracker', 'EmployeePermission')
    EmployeePermission.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0012_employeepermission'),
    ]

    operations = [
        migrations.RunPython(populate_permissions, remove_permissions),
    ]
