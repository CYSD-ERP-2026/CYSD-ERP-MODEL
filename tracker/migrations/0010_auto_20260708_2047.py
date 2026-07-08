from django.db import migrations

def assign_default_enterprise(apps, schema_editor):
    Enterprise = apps.get_model('tracker', 'Enterprise')
    Domain = apps.get_model('tracker', 'Domain')
    Employee = apps.get_model('tracker', 'Employee')
    Meeting = apps.get_model('tracker', 'Meeting')
    Project = apps.get_model('tracker', 'Project')
    Task = apps.get_model('tracker', 'Task')
    TaskChecklist = apps.get_model('tracker', 'TaskChecklist')

    # Get or create the default enterprise (CYSD)
    default_enterprise, _ = Enterprise.objects.get_or_create(
        subdomain='cysd',
        defaults={'name': 'CYSD (Centre for Youth and Social Development)'}
    )

    # Assign default enterprise to all existing rows
    Domain.objects.filter(enterprise__isnull=True).update(enterprise=default_enterprise)
    Employee.objects.filter(enterprise__isnull=True).update(enterprise=default_enterprise)
    Meeting.objects.filter(enterprise__isnull=True).update(enterprise=default_enterprise)
    Project.objects.filter(enterprise__isnull=True).update(enterprise=default_enterprise)
    Task.objects.filter(enterprise__isnull=True).update(enterprise=default_enterprise)
    TaskChecklist.objects.filter(enterprise__isnull=True).update(enterprise=default_enterprise)

def reverse_default_enterprise(apps, schema_editor):
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0009_enterprise_delete_organizationprofile_and_more'),
    ]

    operations = [
        migrations.RunPython(assign_default_enterprise, reverse_default_enterprise),
    ]
