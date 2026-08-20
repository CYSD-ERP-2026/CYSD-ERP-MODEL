"""
CYSD ERP – Django Admin Configuration
======================================
Provides richly configured admin views for:
  • Domain   – list, search, toggle active
  • Employee – list, filters, search, inline photo preview
  • Meeting  – list, filters, search, attendees widget, inline action

All admin classes use list_display, list_filter, search_fields,
readonly_fields, fieldsets, and inline/action hooks so data entry
and review from the Django admin is quick and ergonomic.
"""
from django import forms
from django.contrib import admin
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from import_export import fields, resources
from import_export.admin import ImportExportModelAdmin
from import_export.widgets import ForeignKeyWidget, ManyToManyWidget
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.import_export.forms import ExportForm, ImportForm

from .models import (
    Domain,
    Employee,
    EmployeePermission,
    EmployeeStats,
    Meeting,
    Project,
    Task,
    TaskChecklist,
)

# ===========================================================================
# Domain Admin
# ===========================================================================

@admin.register(Domain)
class DomainAdmin(ModelAdmin):
    list_display = ('name', 'code', 'lead', 'active_employee_count_display', 'is_active', 'created_at')
    list_display_links = ('name',)
    list_filter = ('is_active',)
    search_fields = ('name', 'code', 'lead')
    list_editable = ('is_active',)
    ordering = ('name',)
    readonly_fields = ('created_at', 'updated_at', 'active_employee_count_display')

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'code', 'description'),
        }),
        ('Management', {
            'fields': ('lead', 'is_active'),
        }),
        ('Timestamps', {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at'),
        }),
    )

    @admin.display(description='Active Staff')
    def active_employee_count_display(self, obj):
        count = obj.active_employee_count
        colour = '#2e7d32' if count > 0 else '#9e9e9e'
        return format_html(
            '<span style="color:{}; font-weight:bold;">{}</span>',
            colour,
            count,
        )

    actions = ['mark_active', 'mark_inactive']

    @admin.action(description='Mark selected domains as Active')
    def mark_active(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} domain(s) marked as active.')

    @admin.action(description='Mark selected domains as Inactive')
    def mark_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} domain(s) marked as inactive.')


# ===========================================================================
# Employee Admin
# ===========================================================================

class EmployeeAdminForm(forms.ModelForm):
    custom_username = forms.CharField(
        max_length=150,
        required=False,
        label="Username (new user account)",
        help_text="Required when creating a new employee without a linked user."
    )
    custom_password = forms.CharField(
        widget=forms.PasswordInput(render_value=False),
        required=False,
        label="Password (new user account)",
        help_text="Required when creating a new employee without a linked user."
    )

    class Meta:
        model = Employee
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Required only on creation
        if not self.instance.pk:
            self.fields['custom_username'].required = True
            self.fields['custom_password'].required = True
        else:
            self.fields['custom_username'].required = False
            self.fields['custom_password'].required = False

    def clean_custom_username(self):
        username = self.cleaned_data.get('custom_username')
        if not self.instance.pk and username:
            if User.objects.filter(username=username).exists():
                raise forms.ValidationError("A user with this username already exists.")
        return username

    def save(self, commit=True):
        employee = super().save(commit=False)
        if not employee.pk and not employee.user:
            username = self.cleaned_data.get('custom_username')
            password = self.cleaned_data.get('custom_password')
            if username and password:
                user = User.objects.create_user(
                    username=username,
                    password=password,
                    email=employee.email
                )
                user.is_superuser = False
                user.save()
                employee.user = user
        if commit:
            employee.save()
        return employee


# ---------------------------------------------------------------------------
# EmployeePermission Inline
# ---------------------------------------------------------------------------

class EmployeePermissionInline(TabularInline):
    """
    Inline that surfaces all EmployeePermission fields directly inside the
    Employee change page in the admin.  This is the single canonical place
    to manage per-employee access controls — the frontend ERP modal no
    longer exposes a permissions form.
    """
    model = EmployeePermission
    can_delete = False
    verbose_name = "Permissions"
    verbose_name_plural = "Access Permissions"
    extra = 0  # row is auto-created by signal; no blank extra rows needed

    # Show every field so admins have full visibility in one place
    fields = (
        # Boolean flags
        'can_manage_employees',
        'can_manage_organization',
        'can_assign_checklist_items',
        'can_approve_checklist_items',
        'can_schedule_meetings',
        'can_read_confidential_meetings',
        'can_access_admin_panel',
        'can_self_assign_tasks',
        'can_view_employee_analytics',
        # Scope selectors
        'checklist_assign_scope',
        'checklist_approve_scope',
        'employee_analytics_scope',
    )

    def has_add_permission(self, request, obj=None):
        # The row is created automatically by signal; manual add not needed
        return False


class EmployeeResource(resources.ModelResource):
    """
    Enhanced import/export resource that adds virtual ``username`` and
    ``password`` columns and properly resolves M2M domains and the
    self-referential supervisor FK.

    Import behaviour:
    • If a ``username`` is provided, a Django ``User`` is created (or
      updated) and linked to the employee.
    • If ``password`` is provided (and is not the masked placeholder),
      the user's password is set to that value.
    • ``domains`` accepts pipe-separated domain names (e.g. "Education|Health").
    • ``supervisor`` is looked up by ``employee_id``.

    Export behaviour:
    • ``username`` → the linked user's username (or blank).
    • ``password`` → always ``"********"`` (hashed passwords cannot be exported).
    """

    username = fields.Field(column_name='username')
    password = fields.Field(column_name='password')
    domains = fields.Field(
        column_name='domains',
        attribute='domains',
        widget=ManyToManyWidget(Domain, separator='|', field='name'),
    )
    supervisor = fields.Field(
        column_name='supervisor',
        attribute='supervisor',
        widget=ForeignKeyWidget(Employee, field='employee_id'),
    )

    class Meta:
        model = Employee
        import_id_fields = ('employee_id',)
        skip_unchanged = True
        report_skipped = True
        fields = (
            'employee_id', 'name', 'username', 'password',
            'email', 'phone', 'designation', 'employment_type',
            'gender', 'date_of_birth', 'date_joined',
            'domains', 'supervisor', 'is_active', 'address', 'notes',
        )
        export_order = fields

    # ── Export helpers ────────────────────────────────────────────────────
    def dehydrate_username(self, employee):
        return employee.user.username if employee.user else ''

    def dehydrate_password(self, employee):
        return '********'

    # ── Import hook: create / update linked User ─────────────────────────
    def after_save_instance(self, instance, row, **kwargs):
        username = row.get('username', '').strip()
        password = row.get('password', '').strip()

        if not username:
            return

        if instance.user:
            # Update existing linked user
            user = instance.user
            changed = False
            if user.username != username:
                user.username = username
                changed = True
            if password and password != '********':
                user.set_password(password)
                changed = True
            if user.email != instance.email:
                user.email = instance.email
                changed = True
            if changed:
                user.save()
        else:
            # Create or link a user account
            try:
                user = User.objects.get(username=username)
                if password and password != '********':
                    user.set_password(password)
                    user.save()
            except User.DoesNotExist:
                actual_pw = password if (password and password != '********') else 'ChangeMe@123'
                user = User.objects.create_user(
                    username=username,
                    password=actual_pw,
                    email=instance.email,
                )
            instance.user = user
            instance.save(update_fields=['user'])


@admin.register(Employee)
class EmployeeAdmin(ModelAdmin, ImportExportModelAdmin):
    resource_classes = [EmployeeResource]
    import_form_class = ImportForm
    export_form_class = ExportForm
    form = EmployeeAdminForm
    inlines = [EmployeePermissionInline]
    list_display = (
        'employee_id', 'name', 'supervisor', 'get_domains', 'get_projects', 'designation',
        'employment_type', 'email', 'is_active', 'date_joined',
    )
    list_display_links = ('employee_id', 'name')
    list_filter = ('domains', 'projects', 'employment_type', 'gender', 'is_active')
    search_fields = ('name', 'employee_id', 'email', 'designation', 'phone')
    list_editable = ('is_active',)
    autocomplete_fields = ('domains', 'projects', 'supervisor')
    raw_id_fields = ('user',)
    date_hierarchy = 'date_joined'
    ordering = ('name',)
    readonly_fields = ('created_at', 'updated_at', 'photo_preview')

    fieldsets = (
        ('User Account', {
            'fields': ('custom_username', 'custom_password', 'user', 'supervisor'),
        }),
        ('Personal Details', {
            'fields': (
                'name', 'employee_id', 'gender', 'date_of_birth',
                'profile_photo', 'photo_preview',
            ),
        }),
        ('Role & Employment', {
            'fields': (
                'domains', 'projects', 'designation', 'employment_type',
                'date_joined', 'date_left', 'is_active',
            ),
        }),
        ('Contact Information', {
            'fields': ('email', 'phone', 'address'),
        }),
        ('Additional Notes', {
            'classes': ('collapse',),
            'fields': ('notes',),
        }),
        ('Record Timestamps', {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at'),
        }),
    )

    @admin.display(description='Domains')
    def get_domains(self, obj):
        return ", ".join([d.name for d in obj.domains.all()])

    @admin.display(description='Projects')
    def get_projects(self, obj):
        return ", ".join([p.title for p in obj.projects.all()])

    @admin.display(description='Current Photo')
    def photo_preview(self, obj):
        if obj.profile_photo:
            return format_html(
                '<img src="{}" style="max-height:120px; max-width:120px; '
                'object-fit:cover; border-radius:6px; border:1px solid #ddd;" />',
                obj.profile_photo.url,
            )
        return mark_safe('<span style="color:#9e9e9e;">No photo uploaded</span>')

    actions = ['activate_employees', 'deactivate_employees']

    @admin.action(description='Activate selected employees')
    def activate_employees(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} employee(s) activated.')

    @admin.action(description='Deactivate selected employees')
    def deactivate_employees(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} employee(s) deactivated.')


# ===========================================================================
# Meeting Admin
# ===========================================================================

class MeetingAttendeeInline(TabularInline):
    """
    Inline used within MeetingAdmin to display and edit the M2M attendee list.
    We use a raw_id / filter_horizontal approach at the main form level,
    but this inline gives a quick glance at who's attending.
    """
    model = Meeting.attendees.through
    extra = 1
    verbose_name = 'Attendee'
    verbose_name_plural = 'Attendees'
    autocomplete_fields = ('employee',)


@admin.register(Meeting)
class MeetingAdmin(ModelAdmin):
    list_display = (
        'title', 'domain', 'meeting_type', 'status_badge',
        'date', 'start_time', 'venue', 'attendee_count_display', 'organised_by',
    )
    list_display_links = ('title',)
    list_filter = ('status', 'meeting_type', 'domain', 'date')
    search_fields = ('title', 'venue', 'organised_by', 'agenda', 'minutes')
    autocomplete_fields = ('attendees', 'organizer', 'convenor', 'facilitator', 'rapporteur')
    date_hierarchy = 'date'
    ordering = ('-date', '-start_time')
    readonly_fields = ('created_at', 'updated_at', 'attendee_count_display')

    fieldsets = (
        ('Meeting Identity', {
            'fields': ('title', 'domain', 'meeting_type', 'status'),
        }),
        ('Schedule & Location', {
            'fields': ('date', 'start_time', 'end_time', 'venue', 'organised_by'),
        }),
        ('Meeting Roles', {
            'description': 'Assign key governance roles for this meeting.',
            'fields': ('organizer', 'convenor', 'facilitator', 'rapporteur'),
        }),
        ('Content', {
            'fields': ('agenda', 'attendees', 'minutes', 'action_points'),
        }),
        ('Attachment', {
            'classes': ('collapse',),
            'fields': ('attachment',),
        }),
        ('Record Timestamps', {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at'),
        }),
    )

    @admin.display(description='Status')
    def status_badge(self, obj):
        colours = {
            'scheduled': '#1565c0',
            'completed': '#2e7d32',
            'cancelled': '#c62828',
            'postponed': '#e65100',
        }
        colour = colours.get(obj.status, '#616161')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:10px;font-size:11px;font-weight:bold;">{}</span>',
            colour,
            obj.get_status_display(),
        )

    @admin.display(description='Attendees')
    def attendee_count_display(self, obj):
        return obj.attendee_count

    actions = ['mark_completed', 'mark_cancelled']

    @admin.action(description='Mark selected meetings as Completed')
    def mark_completed(self, request, queryset):
        updated = queryset.update(status='completed')
        self.message_user(request, f'{updated} meeting(s) marked as completed.')

    @admin.action(description='Mark selected meetings as Cancelled')
    def mark_cancelled(self, request, queryset):
        updated = queryset.update(status='cancelled')
        self.message_user(request, f'{updated} meeting(s) marked as cancelled.')


# ===========================================================================
# Project Admin
# ===========================================================================

@admin.register(Project)
class ProjectAdmin(ModelAdmin):
    list_display = ('title', 'domain', 'start_date', 'deadline', 'status_badge', 'lead_employee')
    list_filter = ('status', 'domain', 'start_date', 'deadline')
    search_fields = ('title', 'domain__name', 'lead_employee__name')
    autocomplete_fields = ('domain', 'lead_employee')
    ordering = ('deadline', 'title')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Project details', {
            'fields': ('title', 'domain', 'status', 'lead_employee'),
        }),
        ('Schedule', {
            'fields': ('start_date', 'deadline'),
        }),
        ('Record Timestamps', {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at'),
        }),
    )

    @admin.display(description='Status')
    def status_badge(self, obj):
        colours = {
            'planning': '#1565c0',
            'active': '#2e7d32',
            'completed': '#4a148c',
            'delayed': '#c62828',
        }
        colour = colours.get(obj.status, '#616161')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:10px;font-size:11px;font-weight:bold;">{}</span>',
            colour,
            obj.get_status_display(),
        )


# ===========================================================================
# Task Admin
# ===========================================================================

@admin.register(Task)
class TaskAdmin(ModelAdmin):
    list_display = ('title', 'project', 'display_assigned_to', 'due_date', 'status_badge')
    list_filter = ('status', 'project', 'assigned_to', 'due_date')
    search_fields = ('title', 'project__title', 'assigned_to__name')
    autocomplete_fields = ('project', 'assigned_to')
    ordering = ('due_date', 'title')
    readonly_fields = ('created_at', 'updated_at')

    def display_assigned_to(self, obj):
        return ", ".join([emp.name for emp in obj.assigned_to.all()])
    display_assigned_to.short_description = 'Assigned To'

    fieldsets = (
        ('Task details', {
            'fields': ('title', 'project', 'assigned_to', 'status'),
        }),
        ('Schedule', {
            'fields': ('due_date',),
        }),
        ('Record Timestamps', {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at'),
        }),
    )

    @admin.display(description='Status')
    def status_badge(self, obj):
        colours = {
            'pending': '#1565c0',
            'in_progress': '#e65100',
            'completed': '#2e7d32',
            'overdue': '#c62828',
        }
        colour = colours.get(obj.status, '#616161')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:10px;font-size:11px;font-weight:bold;">{}</span>',
            colour,
            obj.get_status_display(),
        )



# ===========================================================================
# TaskChecklist Admin
# ===========================================================================

@admin.register(TaskChecklist)
class TaskChecklistAdmin(ModelAdmin):
    list_display = (
        'title', 'assigned_to', 'created_by', 'status_badge',
        'submitted_at', 'resolved_at', 'created_at',
    )
    list_filter = ('status', 'assigned_to__domains', 'created_at')
    search_fields = ('title', 'assigned_to__name', 'created_by__name', 'description')
    autocomplete_fields = ('assigned_to', 'created_by')
    ordering = ('-created_at',)
    readonly_fields = ('submitted_at', 'resolved_at', 'created_at', 'updated_at')

    def has_add_permission(self, request):
        if not super().has_add_permission(request):
            return False
        if request.user.is_superuser:
            return True
        profile = getattr(request.user, 'employee_profile', None)
        return bool(profile and hasattr(profile, 'permissions') and profile.permissions.can_assign_checklist_items)


    fieldsets = (
        ('Task Details', {
            'fields': ('title', 'description', 'assigned_to', 'created_by'),
        }),
        ('Workflow Status', {
            'fields': ('status', 'rejection_feedback'),
        }),
        ('Timestamps', {
            'classes': ('collapse',),
            'fields': ('submitted_at', 'resolved_at', 'created_at', 'updated_at'),
        }),
    )

    @admin.display(description='Status')
    def status_badge(self, obj):
        colours = {
            'PENDING':               '#1565c0',
            'AWAITING_VERIFICATION': '#e65100',
            'COMPLETED':             '#2e7d32',
        }
        colour = colours.get(obj.status, '#616161')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 10px;'
            'border-radius:12px;font-size:11px;font-weight:bold;">{}</span>',
            colour,
            obj.get_status_display(),
        )

    actions = ['mark_completed', 'reset_to_pending']

    @admin.action(description='Force-complete selected items')
    def mark_completed(self, request, queryset):
        affected_employee_ids = set(queryset.values_list('assigned_to_id', flat=True))
        updated = queryset.update(
            status='COMPLETED',
            resolved_at=timezone.now(),
        )
        # Recalculate stats for all affected employees (deduplicated)
        for emp in Employee.objects.filter(id__in=affected_employee_ids):
            EmployeeStats.recalculate_for(emp)
        self.message_user(request, f'{updated} item(s) marked as completed.')

    @admin.action(description='Reset selected items to Pending')
    def reset_to_pending(self, request, queryset):
        affected_employee_ids = set(queryset.values_list('assigned_to_id', flat=True))
        updated = queryset.update(
            status='PENDING',
            submitted_at=None,
            rejection_feedback='',
        )
        # Recalculate stats for all affected employees (deduplicated)
        for emp in Employee.objects.filter(id__in=affected_employee_ids):
            EmployeeStats.recalculate_for(emp)
        self.message_user(request, f'{updated} item(s) reset to Pending.')


# ===========================================================================
# EmployeeStats Admin  (read-only analytics view)
# ===========================================================================

@admin.register(EmployeeStats)
class EmployeeStatsAdmin(ModelAdmin):
    list_display = (
        'employee', 'total_assigned', 'total_completed',
        'total_awaiting', 'total_pending',
        'completion_pct_display', 'last_recalculated',
    )
    list_filter  = ('employee__domains',)
    search_fields = ('employee__name', 'employee__employee_id')
    ordering = ('-completion_percentage',)
    readonly_fields = (
        'employee', 'total_assigned', 'total_completed',
        'total_pending', 'total_awaiting',
        'completion_percentage', 'last_recalculated',
    )

    def has_add_permission(self, request):
        return False  # rows are created/updated programmatically by signals

    @admin.display(description='Completion %')
    def completion_pct_display(self, obj):
        pct = float(obj.completion_percentage)
        colour = '#2e7d32' if pct >= 75 else ('#e65100' if pct >= 40 else '#c62828')
        return format_html(
            '<span style="color:{};font-weight:bold;">{}%</span>',
            colour, f"{pct:.1f}",
        )
