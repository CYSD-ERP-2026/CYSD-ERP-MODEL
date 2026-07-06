# Generated migration for tracker app
# Models: Domain, Employee, Meeting

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        # ------------------------------------------------------------------ #
        # Domain
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name='Domain',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(
                    max_length=150,
                    unique=True,
                    help_text='Name of the programme domain (e.g. "Education", "Health")',
                )),
                ('code', models.CharField(
                    max_length=20,
                    unique=True,
                    help_text='Short identifier code (e.g. "EDU", "HLT")',
                )),
                ('description', models.TextField(
                    blank=True,
                    help_text="Brief description of the domain's mandate and activities",
                )),
                ('lead', models.CharField(
                    blank=True,
                    max_length=150,
                    help_text='Name of the domain lead / focal person',
                )),
                ('is_active', models.BooleanField(
                    default=True,
                    help_text='Whether this domain is currently operational',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Domain',
                'verbose_name_plural': 'Domains',
                'ordering': ['name'],
            },
        ),

        # ------------------------------------------------------------------ #
        # Employee
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name='Employee',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('employee_id', models.CharField(
                    max_length=30,
                    unique=True,
                    help_text='Unique employee / volunteer ID (e.g. "CYSD-2024-001")',
                )),
                ('name', models.CharField(max_length=200)),
                ('gender', models.CharField(
                    blank=True,
                    max_length=1,
                    choices=[
                        ('M', 'Male'),
                        ('F', 'Female'),
                        ('O', 'Other'),
                        ('N', 'Prefer not to say'),
                    ],
                )),
                ('date_of_birth', models.DateField(blank=True, null=True)),
                ('profile_photo', models.ImageField(
                    blank=True,
                    null=True,
                    upload_to='employees/photos/',
                )),
                ('domain', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='employees',
                    to='tracker.domain',
                    help_text='Primary programme domain the employee works in',
                )),
                ('designation', models.CharField(
                    max_length=150,
                    help_text='Job title or designation (e.g. "Field Coordinator")',
                )),
                ('employment_type', models.CharField(
                    default='full_time',
                    max_length=20,
                    choices=[
                        ('full_time', 'Full-Time'),
                        ('part_time', 'Part-Time'),
                        ('contractual', 'Contractual'),
                        ('volunteer', 'Volunteer'),
                        ('intern', 'Intern'),
                    ],
                )),
                ('date_joined', models.DateField(default=django.utils.timezone.now)),
                ('date_left', models.DateField(
                    blank=True,
                    null=True,
                    help_text='Leave blank if still employed',
                )),
                ('is_active', models.BooleanField(default=True)),
                ('email', models.EmailField(max_length=254, unique=True)),
                ('phone', models.CharField(blank=True, max_length=20)),
                ('address', models.TextField(blank=True)),
                ('notes', models.TextField(
                    blank=True,
                    help_text='Any additional notes about this employee',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Employee',
                'verbose_name_plural': 'Employees',
                'ordering': ['name'],
                'indexes': [
                    models.Index(fields=['domain', 'is_active'], name='tracker_emp_domain_i_idx'),
                    models.Index(fields=['employment_type'], name='tracker_emp_emp_type_idx'),
                ],
            },
        ),

        # ------------------------------------------------------------------ #
        # Meeting
        # ------------------------------------------------------------------ #
        migrations.CreateModel(
            name='Meeting',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(
                    max_length=250,
                    help_text='Short, descriptive title of the meeting',
                )),
                ('domain', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='meetings',
                    to='tracker.domain',
                    help_text='Domain this meeting is associated with',
                )),
                ('meeting_type', models.CharField(
                    default='internal',
                    max_length=20,
                    choices=[
                        ('internal', 'Internal Review'),
                        ('field', 'Field Visit'),
                        ('partner', 'Partner / Stakeholder Meeting'),
                        ('training', 'Training / Workshop'),
                        ('board', 'Board / Governance Meeting'),
                        ('other', 'Other'),
                    ],
                )),
                ('status', models.CharField(
                    default='scheduled',
                    max_length=20,
                    choices=[
                        ('scheduled', 'Scheduled'),
                        ('completed', 'Completed'),
                        ('cancelled', 'Cancelled'),
                        ('postponed', 'Postponed'),
                    ],
                )),
                ('date', models.DateField(help_text='Date of the meeting')),
                ('start_time', models.TimeField(blank=True, null=True)),
                ('end_time', models.TimeField(blank=True, null=True)),
                ('venue', models.CharField(
                    blank=True,
                    max_length=250,
                    help_text='Physical location or video-call link',
                )),
                ('agenda', models.TextField(
                    blank=True,
                    help_text='Meeting agenda / objectives',
                )),
                ('attendees', models.ManyToManyField(
                    blank=True,
                    related_name='meetings_attended',
                    to='tracker.employee',
                    help_text='Employees who attended or are invited to this meeting',
                )),
                ('minutes', models.TextField(
                    blank=True,
                    help_text='Meeting minutes / notes recorded during the meeting',
                )),
                ('action_points', models.TextField(
                    blank=True,
                    help_text='Action points agreed upon, one per line',
                )),
                ('attachment', models.FileField(
                    blank=True,
                    null=True,
                    upload_to='meetings/attachments/',
                    help_text='Upload meeting agenda, minutes document, or presentation',
                )),
                ('organised_by', models.CharField(
                    blank=True,
                    max_length=150,
                    help_text='Name of the person who organised this meeting',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Meeting',
                'verbose_name_plural': 'Meetings',
                'ordering': ['-date', '-start_time'],
                'indexes': [
                    models.Index(fields=['domain', 'date'], name='tracker_mtg_domain_date_idx'),
                    models.Index(fields=['status', 'date'], name='tracker_mtg_status_date_idx'),
                ],
            },
        ),
    ]
