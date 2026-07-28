from django.db import migrations, models
import django.db.models.deletion

def seed_roles(apps, schema_editor):
    Enterprise = apps.get_model('tracker', 'Enterprise')
    Role = apps.get_model('tracker', 'Role')
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
            'can_manage_roles': False,
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
            'can_read_confidential_meetings': False,
            'can_log_hours': True,
            'can_access_admin_panel': True,
            'can_manage_roles': False,
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
            'can_read_confidential_meetings': True,
            'can_log_hours': True,
            'can_access_admin_panel': True,
            'can_manage_roles': False,
            'checklist_assign_scope': 'own_team',
            'checklist_approve_scope': 'own_team',
            'analytics_scope': 'own_team',
        },
        '_default': {
            'can_manage_employees': False,
            'can_manage_organization': False,
            'can_view_advanced_analytics': False,
            'can_assign_checklist_items': False,
            'can_approve_checklist_items': False,
            'can_read_confidential_meetings': True,
            'can_log_hours': True,
            'can_access_admin_panel': False,
            'can_manage_roles': False,
            'checklist_assign_scope': 'none',
            'checklist_approve_scope': 'none',
            'analytics_scope': 'none',
        },
    }
    for enterprise in Enterprise.objects.all().iterator():
        for role_name in ['founder', 'hr', 'supervisor', 'employee', 'intern', 'volunteer']:
            perms = ROLE_PERMISSION_MAP.get(role_name, ROLE_PERMISSION_MAP['_default'])
            Role.objects.create(
                enterprise=enterprise,
                name=role_name,
                description=f"System default {role_name} role",
                is_system_default=True,
                **perms,
            )

def link_role_tag(apps, schema_editor):
    Employee = apps.get_model('tracker', 'Employee')
    Role = apps.get_model('tracker', 'Role')
    for emp in Employee.objects.all().iterator():
        try:
            role_obj = Role.objects.get(enterprise=emp.enterprise, name=emp.role)
            emp.role_tag = role_obj
            emp.save(update_fields=['role_tag'])
        except Role.DoesNotExist:
            continue

def reverse_seed_roles(apps, schema_editor):
    Role = apps.get_model('tracker', 'Role')
    Role.objects.all().delete()

def reverse_link_role_tag(apps, schema_editor):
    Employee = apps.get_model('tracker', 'Employee')
    Employee.objects.update(role_tag=None)

class Migration(migrations.Migration):
    dependencies = [
        ('tracker', '0013_populate_employeepermission'),
    ]
    operations = [
        migrations.AddField(
            model_name='employeepermission',
            name='can_manage_roles',
            field=models.BooleanField(default=False, help_text='Can create / edit / delete Role tags for the enterprise'),
        ),
        migrations.CreateModel(
            name='Role',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50, help_text='Name of the role tag')),
                ('description', models.TextField(blank=True, help_text='Optional description of the role')),
                ('can_manage_employees', models.BooleanField(default=False)),
                ('can_manage_organization', models.BooleanField(default=False)),
                ('can_view_advanced_analytics', models.BooleanField(default=False)),
                ('can_assign_checklist_items', models.BooleanField(default=False)),
                ('can_approve_checklist_items', models.BooleanField(default=False)),
                ('can_read_confidential_meetings', models.BooleanField(default=False)),
                ('can_log_hours', models.BooleanField(default=False)),
                ('can_access_admin_panel', models.BooleanField(default=False)),
                ('can_manage_roles', models.BooleanField(default=False)),
                ('checklist_assign_scope', models.CharField(choices=[('none', 'None'), ('own_team', 'Own Team'), ('all', 'All')], default='none', max_length=10)),
                ('checklist_approve_scope', models.CharField(choices=[('none', 'None'), ('own_team', 'Own Team'), ('all', 'All')], default='none', max_length=10)),
                ('analytics_scope', models.CharField(choices=[('none', 'None'), ('own_team', 'Own Team'), ('all', 'All')], default='none', max_length=10)),
                ('is_system_default', models.BooleanField(default=False, help_text='Marks the original seeded roles; editable but flagged for warnings before deletion')),
                ('enterprise', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='roles', to='tracker.Enterprise')),
            ],
            options={
                'verbose_name': 'Role',
                'verbose_name_plural': 'Roles',
                'unique_together': {('enterprise', 'name')},
            },
        ),
        migrations.AddField(
            model_name='employee',
            name='role_tag',
            field=models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name='employees', to='tracker.Role'),
        ),
        migrations.RunPython(seed_roles, reverse_seed_roles),
        migrations.RunPython(link_role_tag, reverse_link_role_tag),
    ]
