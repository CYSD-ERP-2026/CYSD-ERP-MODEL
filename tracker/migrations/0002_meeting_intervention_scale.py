from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='meeting',
            name='intervention_scale',
            field=models.CharField(
                choices=[
                    ('individual', 'Individual'),
                    ('community', 'Community'),
                    ('district', 'District'),
                    ('state', 'State'),
                    ('national', 'National'),
                ],
                default='community',
                help_text='Geographic / operational scale at which this meeting intervenes',
                max_length=20,
            ),
        ),
    ]
