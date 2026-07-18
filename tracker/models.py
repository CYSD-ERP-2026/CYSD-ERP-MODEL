"""
CYSD ERP Tracker Models
=======================
Core data models for the NGO's enterprise resource planning dashboard.

Models:
    Domain   – Thematic programme area (e.g. Education, Health, Livelihood)
    Employee – Staff / volunteer record linked to a Domain
    Meeting  – Scheduled / completed meeting record linked to a Domain
"""
from pathlib import Path

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

MAX_UPLOAD_SIZE = 5 * 1024 * 1024
ALLOWED_DOCUMENT_EXTENSIONS = {'.pdf', '.doc', '.docx', '.txt', '.xls', '.xlsx', '.ppt', '.pptx'}
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}


def validate_upload_size(upload):
    if upload and getattr(upload, 'size', 0) > MAX_UPLOAD_SIZE:
        raise ValidationError(f'File size exceeds the {MAX_UPLOAD_SIZE // (1024 * 1024)}MB limit.')
    return upload


def validate_document_file(upload):
    if not upload:
        return upload
    validate_upload_size(upload)
    filename = getattr(upload, 'name', '') or ''
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise ValidationError('Unsupported document type. Use PDF, DOC, DOCX, TXT, XLS, XLSX, PPT, or PPTX.')
    return upload


def validate_image_file(upload):
    if not upload:
        return upload
    validate_upload_size(upload)
    filename = getattr(upload, 'name', '') or ''
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError('Unsupported image type. Use JPG, JPEG, PNG, or WEBP.')
    return upload


# ---------------------------------------------------------------------------
# Domain
# ---------------------------------------------------------------------------

class Domain(models.Model):
    """
    A thematic programme domain / department of the NGO.

    Example domains: Education, Health, Livelihood, WASH, Child Protection.
    """
    enterprise = models.ForeignKey(
        'Enterprise',
        on_delete=models.CASCADE,
        related_name='%(class)ss',
        null=False,
    )
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
    def active_employee_count(self) -> int:
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


ROLE_CHOICES = [
    ('founder', 'Founder'),
    ('hr', 'HR'),
    ('supervisor', 'Supervisor'),
    ('employee', 'Employee'),
    ('intern', 'Intern'),
    ('volunteer', 'Volunteer'),
]


class Employee(models.Model):
    """
    Staff / volunteer record for the NGO.

    Each employee belongs to one primary Domain and has a designation,
    contact details, and employment metadata.
    """
    enterprise = models.ForeignKey(
        'Enterprise',
        on_delete=models.CASCADE,
        related_name='%(class)ss',
        null=False,
    )
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='employee_profile',
        help_text="Django user account linked to this employee profile"
    )
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='employee',
        help_text="Role-Based Access Control level"
    )
    supervisor = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='subordinates',
        help_text="Supervisor this employee reports directly to"
    )
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
        validators=[validate_image_file],
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
            models.Index(fields=['domain', 'is_active'], name='tracker_emp_domain_i_idx'),
            models.Index(fields=['employment_type'], name='tracker_emp_emp_type_idx'),
        ]

    def __str__(self):
        return f'{self.name} – {self.designation} [{self.employee_id}]'

    @property
    def is_currently_active(self) -> bool:
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
    enterprise = models.ForeignKey(
        'Enterprise',
        on_delete=models.CASCADE,
        related_name='%(class)ss',
        null=False,
    )
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
        validators=[validate_document_file],
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
            models.Index(fields=['domain', 'date'], name='tracker_mtg_domain_date_idx'),
            models.Index(fields=['status', 'date'], name='tracker_mtg_status_date_idx'),
        ]

    def __str__(self):
        return f'{self.title} | {self.date} [{self.get_status_display()}]'

    @property
    def attendee_count(self) -> int:
        return self.attendees.count()


# ---------------------------------------------------------------------------
# Project & Task (Employee Performance & Workload expansion)
# ---------------------------------------------------------------------------

PROJECT_STATUS_CHOICES = [
    ('planning', 'Planning'),
    ('active', 'Active'),
    ('completed', 'Completed'),
    ('delayed', 'Delayed'),
]

TASK_STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('in_progress', 'In Progress'),
    ('completed', 'Completed'),
    ('overdue', 'Overdue'),
]


class Project(models.Model):
    enterprise = models.ForeignKey(
        'Enterprise',
        on_delete=models.CASCADE,
        related_name='%(class)ss',
        null=False,
    )
    title = models.CharField(max_length=250, help_text="Title of the project")
    domain = models.ForeignKey(
        Domain,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='projects',
        help_text="Thematic domain this project belongs to"
    )
    start_date = models.DateField(default=timezone.now)
    deadline = models.DateField(help_text="Project deadline date")
    status = models.CharField(
        max_length=20,
        choices=PROJECT_STATUS_CHOICES,
        default='planning'
    )
    lead_employee = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='led_projects',
        help_text="Employee leading this project"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['deadline', 'title']
        verbose_name = 'Project'
        verbose_name_plural = 'Projects'

    def __str__(self):
        return f"{self.title} [{self.get_status_display()}]"


class Task(models.Model):
    enterprise = models.ForeignKey(
        'Enterprise',
        on_delete=models.CASCADE,
        related_name='%(class)ss',
        null=False,
    )
    title = models.CharField(max_length=250, help_text="Task description / title")
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='tasks',
        help_text="Project this task belongs to"
    )
    assigned_to = models.ManyToManyField(
        Employee,
        related_name='tasks',
        help_text="Employees assigned to this task"
    )
    due_date = models.DateField(help_text="Task due date")
    status = models.CharField(
        max_length=20,
        choices=TASK_STATUS_CHOICES,
        default='pending'
    )
    hours_logged = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0.0,
        help_text="Hours logged on this task"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['due_date', 'title']
        verbose_name = 'Task'
        verbose_name_plural = 'Tasks'

    def __str__(self):
        if self.pk:
            assignees = ", ".join([emp.name for emp in self.assigned_to.all()])
            return f"{self.title} – [{assignees}] [{self.get_status_display()}]"
        return f"{self.title} [{self.get_status_display()}]"


# ---------------------------------------------------------------------------
# TaskChecklist  –  multi-phase verification workflow
# ---------------------------------------------------------------------------

CHECKLIST_STATUS_CHOICES = [
    ('PENDING',               'Pending'),
    ('AWAITING_VERIFICATION', 'Awaiting Verification'),
    ('COMPLETED',             'Completed'),
]


class TaskChecklist(models.Model):
    """
    A single checklist item assigned by a Supervisor or Founder to one Employee.

    Lifecycle
    ---------
    PENDING  ──►  AWAITING_VERIFICATION  ──►  COMPLETED
                         │
                         └──► PENDING  (supervisor rejected)

    Creation rules (enforced in clean()):
      • Only roles 'founder', 'hr', or 'supervisor' may create checklist items.
      • A supervisor may only assign tasks to their own direct subordinates.
      • A founder / hr may assign to anyone.
    """
    enterprise = models.ForeignKey(
        'Enterprise',
        on_delete=models.CASCADE,
        related_name='%(class)ss',
        null=False,
    )

    title = models.CharField(
        max_length=250,
        help_text='Short descriptive title of the checklist item',
    )
    description = models.TextField(
        blank=True,
        help_text='Detailed description or acceptance criteria',
    )
    assigned_to = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='checklist_items',
        help_text='Employee this checklist item is assigned to',
    )
    created_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_checklist_items',
        help_text='Supervisor / founder who created this item',
    )
    status = models.CharField(
        max_length=30,
        choices=CHECKLIST_STATUS_CHOICES,
        default='PENDING',
        db_index=True,
    )
    # Populated when a supervisor rejects the submission
    rejection_feedback = models.TextField(
        blank=True,
        help_text='Feedback provided by the supervisor when rejecting a submission',
    )
    # Timestamps for each phase transition
    submitted_at = models.DateTimeField(
        null=True, blank=True,
        help_text='When the employee marked this item as done',
    )
    resolved_at = models.DateTimeField(
        null=True, blank=True,
        help_text='When the supervisor approved or rejected',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Task Checklist Item'
        verbose_name_plural = 'Task Checklist Items'
        indexes = [
            models.Index(
                fields=['assigned_to', 'status'],
                name='tracker_chk_assignee_stat_idx',
            ),
            models.Index(
                fields=['status', 'created_at'],
                name='tracker_chk_status_date_idx',
            ),
        ]

    def __str__(self):
        return f'{self.title} → {self.assigned_to.name} [{self.get_status_display()}]'

    def clean(self):
        """
        Enforce creation / assignment rules using EmployeePermission:
          1. created_by must have can_assign_checklist_items permission.
          2. If checklist_assign_scope is 'own_team', only direct reports
             may be assigned to.
          3. If scope is 'all', any employee in the enterprise may be assigned.
        """
        from django.core.exceptions import ValidationError

        if self.created_by is None:
            return  # skip validation during programmatic creation without a creator

        perms = getattr(self.created_by, 'permissions', None)

        if not perms or not perms.can_assign_checklist_items:
            raise ValidationError(
                f'Only employees with checklist assignment permission can '
                f'create checklist items. '
                f'"{self.created_by.name}" does not have this permission.'
            )

        if perms.checklist_assign_scope == 'own_team':
            # Scoped to own team — only direct reports allowed
            if self.assigned_to.supervisor_id != self.created_by.pk:
                raise ValidationError(
                    f'"{self.created_by.name}" can only assign tasks to '
                    f'their direct reports. "{self.assigned_to.name}" does not report to them.'
                )
        elif perms.checklist_assign_scope == 'none':
            raise ValidationError(
                f'"{self.created_by.name}" has checklist assignment permission '
                f'but scope is set to "none".'
            )
        # scope == 'all' → no restriction on assigned_to


    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# EmployeeStats  –  cached analytics snapshot, refreshed by signal
# ---------------------------------------------------------------------------

class EmployeeStats(models.Model):
    """
    Cached analytics row for each Employee.

    Recalculated atomically every time a TaskChecklist item transitions to
    COMPLETED (via the post_save signal in signals.py).  Reading dashboards
    hit this table instead of running expensive aggregates on every request.
    """
    employee = models.OneToOneField(
        Employee,
        on_delete=models.CASCADE,
        related_name='stats',
        primary_key=True,
    )
    total_assigned = models.PositiveIntegerField(default=0)
    total_completed = models.PositiveIntegerField(default=0)
    total_pending = models.PositiveIntegerField(default=0)
    total_awaiting = models.PositiveIntegerField(default=0)
    # 0.0 – 100.0, stored as DECIMAL for charting precision
    completion_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
    )
    last_recalculated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Employee Stats'
        verbose_name_plural = 'Employee Stats'

    def __str__(self):
        return (
            f'{self.employee.name} – '
            f'{self.completion_percentage}% complete '
            f'({self.total_completed}/{self.total_assigned})'
        )

    @classmethod
    def recalculate_for(cls, employee: 'Employee') -> 'EmployeeStats':
        """
        Atomically recompute all counters for the given employee and
        upsert the stats row.  Called by the post_save signal.
        """
        from django.db.models import Count, Q

        agg = TaskChecklist.objects.filter(assigned_to=employee).aggregate(
            total=Count('id'),
            completed=Count('id', filter=Q(status='COMPLETED')),
            pending=Count('id', filter=Q(status='PENDING')),
            awaiting=Count('id', filter=Q(status='AWAITING_VERIFICATION')),
        )

        total      = agg['total']      or 0
        completed  = agg['completed']  or 0
        pending    = agg['pending']    or 0
        awaiting   = agg['awaiting']   or 0
        pct = round((completed / total) * 100, 2) if total > 0 else 0.00

        stats, _ = cls.objects.update_or_create(
            employee=employee,
            defaults={
                'total_assigned':        total,
                'total_completed':       completed,
                'total_pending':         pending,
                'total_awaiting':        awaiting,
                'completion_percentage': pct,
            },
        )
        return stats


class Enterprise(models.Model):
    """
    Represents a tenant enterprise in the multi-tenant system.
    """
    name = models.CharField(
        max_length=255,
        help_text='Name of the enterprise'
    )
    subdomain = models.CharField(
        max_length=63,
        unique=True,
        help_text='Unique subdomain for routing (e.g. "cysd")'
    )
    logo = models.ImageField(
        upload_to='organization/logos/',
        blank=True,
        null=True,
        validators=[validate_image_file],
        help_text='Upload the enterprise logo'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Enterprise'
        verbose_name_plural = 'Enterprises'

    def __str__(self):
        return f"{self.name} ({self.subdomain})"


# ---------------------------------------------------------------------------
# EmployeePermission  –  fine-grained permission flags per employee
# ---------------------------------------------------------------------------

PERMISSION_SCOPE_CHOICES = [
    ('none', 'None'),
    ('own_team', 'Own Team'),
    ('all', 'All'),
]


class EmployeePermission(models.Model):
    """
    Fine-grained permission record for each Employee.

    Replaces the coarse role-based checks that were previously scattered
    across views, models, and admin forms.  The ``role`` field on Employee
    is retained as a *template*: when a new employee is created, the role
    seeds a default EmployeePermission row using the mapping table defined
    in migration 0013.  Admins can then customise individual flags via the
    toggle UI without touching the role field.

    All boolean fields default to **False** and all scope fields default to
    **'none'** so that a migration or code bug always results in *less*
    access than intended, never more.
    """
    employee = models.OneToOneField(
        Employee,
        on_delete=models.CASCADE,
        related_name='permissions',
        primary_key=True,
    )

    # ── Boolean permission flags (8) ──
    can_manage_employees = models.BooleanField(
        default=False,
        help_text='Can create / edit / deactivate employee records',
    )
    can_manage_organization = models.BooleanField(
        default=False,
        help_text='Can edit enterprise / organisation settings',
    )
    can_view_advanced_analytics = models.BooleanField(
        default=False,
        help_text='Can access the employee-performance analytics page',
    )
    can_assign_checklist_items = models.BooleanField(
        default=False,
        help_text='Can create TaskChecklist items and assign them to employees',
    )
    can_approve_checklist_items = models.BooleanField(
        default=False,
        help_text='Can approve / reject submitted TaskChecklist items',
    )
    can_read_confidential_meetings = models.BooleanField(
        default=False,
        help_text='Can view full meeting agenda, minutes, and action points '
                  '(when False, these fields are masked)',
    )
    can_log_hours = models.BooleanField(
        default=False,
        help_text='Can log hours on tasks assigned to them',
    )
    can_access_admin_panel = models.BooleanField(
        default=False,
        help_text='Grants is_staff + tracker app permissions on the linked User',
    )

    # ── Scope fields (3) ──
    checklist_assign_scope = models.CharField(
        max_length=10,
        choices=PERMISSION_SCOPE_CHOICES,
        default='none',
        help_text="'none' = cannot assign, 'own_team' = direct reports only, "
                  "'all' = any employee in the enterprise",
    )
    checklist_approve_scope = models.CharField(
        max_length=10,
        choices=PERMISSION_SCOPE_CHOICES,
        default='none',
        help_text="'none' = cannot approve, 'own_team' = direct reports only, "
                  "'all' = any employee in the enterprise",
    )
    analytics_scope = models.CharField(
        max_length=10,
        choices=PERMISSION_SCOPE_CHOICES,
        default='none',
        help_text="'none' = own data only, 'own_team' = own direct reports, "
                  "'all' = entire enterprise",
    )

    class Meta:
        verbose_name = 'Employee Permission'
        verbose_name_plural = 'Employee Permissions'

    def __str__(self):
        return f'Permissions for {self.employee.name}'



