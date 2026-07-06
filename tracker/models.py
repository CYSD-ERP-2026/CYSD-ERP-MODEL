"""
CYSD ERP Tracker Models
=======================
Core data models for the NGO's enterprise resource planning dashboard.

Models:
    Domain   – Thematic programme area (e.g. Education, Health, Livelihood)
    Employee – Staff / volunteer record linked to a Domain
    Meeting  – Scheduled / completed meeting record linked to a Domain
"""
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# Domain
# ---------------------------------------------------------------------------

class Domain(models.Model):
    """
    A thematic programme domain / department of the NGO.

    Example domains: Education, Health, Livelihood, WASH, Child Protection.
    """
    name = models.CharField(
        max_length=150,
        unique=True,
        help_text='Name of the programme domain (e.g. "Education", "Health")',
    )
    code = models.CharField(
        max_length=20,
        unique=True,
        help_text='Short identifier code (e.g. "EDU", "HLT")',
    )
    description = models.TextField(
        blank=True,
        help_text='Brief description of the domain\'s mandate and activities',
    )
    lead = models.CharField(
        max_length=150,
        blank=True,
        help_text='Name of the domain lead / focal person',
    )
    is_active = models.BooleanField(
        default=True,
        help_text='Whether this domain is currently operational',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Domain'
        verbose_name_plural = 'Domains'

    def __str__(self):
        return f'{self.name} ({self.code})'

    @property
    def active_employee_count(self):
        return self.employees.filter(is_active=True).count()


# ---------------------------------------------------------------------------
# Employee
# ---------------------------------------------------------------------------

GENDER_CHOICES = [
    ('M', 'Male'),
    ('F', 'Female'),
    ('O', 'Other'),
    ('N', 'Prefer not to say'),
]

EMPLOYMENT_TYPE_CHOICES = [
    ('full_time', 'Full-Time'),
    ('part_time', 'Part-Time'),
    ('contractual', 'Contractual'),
    ('volunteer', 'Volunteer'),
    ('intern', 'Intern'),
]


class Employee(models.Model):
    """
    Staff / volunteer record for the NGO.

    Each employee belongs to one primary Domain and has a designation,
    contact details, and employment metadata.
    """
    # Personal information
    employee_id = models.CharField(
        max_length=30,
        unique=True,
        help_text='Unique employee / volunteer ID (e.g. "CYSD-2024-001")',
    )
    name = models.CharField(max_length=200)
    gender = models.CharField(
        max_length=1,
        choices=GENDER_CHOICES,
        blank=True,
    )
    date_of_birth = models.DateField(
        null=True,
        blank=True,
    )
    profile_photo = models.ImageField(
        upload_to='employees/photos/',
        null=True,
        blank=True,
    )

    # Role & placement
    domain = models.ForeignKey(
        Domain,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employees',
        help_text='Primary programme domain the employee works in',
    )
    designation = models.CharField(
        max_length=150,
        help_text='Job title or designation (e.g. "Field Coordinator")',
    )
    employment_type = models.CharField(
        max_length=20,
        choices=EMPLOYMENT_TYPE_CHOICES,
        default='full_time',
    )
    date_joined = models.DateField(default=timezone.now)
    date_left = models.DateField(
        null=True,
        blank=True,
        help_text='Leave blank if still employed',
    )
    is_active = models.BooleanField(default=True)

    # Contact
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)

    # Metadata
    notes = models.TextField(
        blank=True,
        help_text='Any additional notes about this employee',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Employee'
        verbose_name_plural = 'Employees'
        indexes = [
            models.Index(fields=['domain', 'is_active']),
            models.Index(fields=['employment_type']),
        ]

    def __str__(self):
        return f'{self.name} – {self.designation} [{self.employee_id}]'

    @property
    def is_currently_active(self):
        if not self.is_active:
            return False
        if self.date_left and self.date_left < timezone.now().date():
            return False
        return True


# ---------------------------------------------------------------------------
# Meeting
# ---------------------------------------------------------------------------

MEETING_TYPE_CHOICES = [
    ('internal', 'Internal Review'),
    ('field', 'Field Visit'),
    ('partner', 'Partner / Stakeholder Meeting'),
    ('training', 'Training / Workshop'),
    ('board', 'Board / Governance Meeting'),
    ('other', 'Other'),
]

MEETING_STATUS_CHOICES = [
    ('scheduled', 'Scheduled'),
    ('completed', 'Completed'),
    ('cancelled', 'Cancelled'),
    ('postponed', 'Postponed'),
]

INTERVENTION_SCALE_CHOICES = [
    ('individual', 'Individual'),
    ('community', 'Community'),
    ('district', 'District'),
    ('state', 'State'),
    ('national', 'National'),
]


class Meeting(models.Model):
    """
    A meeting or event record associated with a Domain.

    Stores agenda, attendees, action points, and outcome notes.
    """
    title = models.CharField(
        max_length=250,
        help_text='Short, descriptive title of the meeting',
    )
    domain = models.ForeignKey(
        Domain,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='meetings',
        help_text='Domain this meeting is associated with',
    )
    meeting_type = models.CharField(
        max_length=20,
        choices=MEETING_TYPE_CHOICES,
        default='internal',
    )
    status = models.CharField(
        max_length=20,
        choices=MEETING_STATUS_CHOICES,
        default='scheduled',
    )
    intervention_scale = models.CharField(
        max_length=20,
        choices=INTERVENTION_SCALE_CHOICES,
        default='community',
        help_text='Geographic / operational scale at which this meeting intervenes',
    )

    # Scheduling
    date = models.DateField(help_text='Date of the meeting')
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    venue = models.CharField(
        max_length=250,
        blank=True,
        help_text='Physical location or video-call link',
    )

    # Content
    agenda = models.TextField(
        blank=True,
        help_text='Meeting agenda / objectives',
    )
    attendees = models.ManyToManyField(
        Employee,
        blank=True,
        related_name='meetings_attended',
        help_text='Employees who attended or are invited to this meeting',
    )
    minutes = models.TextField(
        blank=True,
        help_text='Meeting minutes / notes recorded during the meeting',
    )
    action_points = models.TextField(
        blank=True,
        help_text='Action points agreed upon, one per line',
    )
    attachment = models.FileField(
        upload_to='meetings/attachments/',
        null=True,
        blank=True,
        help_text='Upload meeting agenda, minutes document, or presentation',
    )

    # Metadata
    organised_by = models.CharField(
        max_length=150,
        blank=True,
        help_text='Name of the person who organised this meeting',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-start_time']
        verbose_name = 'Meeting'
        verbose_name_plural = 'Meetings'
        indexes = [
            models.Index(fields=['domain', 'date']),
            models.Index(fields=['status', 'date']),
        ]

    def __str__(self):
        return f'{self.title} | {self.date} [{self.get_status_display()}]'

    @property
    def attendee_count(self):
        return self.attendees.count()
