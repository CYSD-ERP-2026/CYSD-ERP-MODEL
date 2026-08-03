# Generated manually on 2026-08-03

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0017_remove_domain_enterprise_remove_employee_enterprise_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='taskchecklist',
            name='is_self_allocated',
            field=models.BooleanField(
                default=False,
                help_text='True when the employee created this task for themselves (self-task allocation)',
            ),
        ),
    ]
