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
from unfold.admin import ModelAdmin, TabularInline

from .models import (
    Domain,
    Employee,
    EmployeeStats,
    Enterprise,
    Meeting,
    Project,
    Task,
    TaskChecklist,
)

# ===========================================================================
# Enterprise Admin
# ===========================================================================

@admin.register(Enterprise)
class EnterpriseAdmin(ModelAdmin):
    list_display = ('name', 'subdomain', 'created_at', 'updated_at')
    search_fields = ('name', 'subdomain')
    readonly_fields = ('created_at', 'updated_at')


class TenantBaseAdmin(ModelAdmin):
    """
    Base Admin class that enforces tenant isolation in Django Admin.
    Filters list querysets, saves records to request.tenant, and filters dropdowns.
    """
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if getattr(request, 'tenant', None):
            if hasattr(qs.model, 'enterprise'):
                return qs.filter(enterprise=request.tenant)
            elif hasattr(qs.model, 'employee'):
                return qs.filter(employee__enterprise=request.tenant)
        return qs

    def save_model(self, request, obj, form, change):
        if getattr(request, 'tenant', None) and hasattr(obj, 'enterprise'):
            obj.enterprise = request.tenant
        super().save_model(request, obj, form, change)

    def get_readonly_fields(self, request, obj=None):
        readonly = super().get_readonly_fields(request, obj) or ()
        if hasattr(self.model, 'enterprise') and 'enterprise' not in readonly:
            return list(readonly) + ['enterprise']
        return readonly

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if getattr(request, 'tenant', None):
            related_model = db_field.related_model
            if hasattr(related_model, 'enterprise'):
                kwargs["queryset"] = related_model.objects.filter(enterprise=request.tenant)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if getattr(request, 'tenant', None):
            related_model = db_field.related_model
            if hasattr(related_model, 'enterprise'):
                kwargs["queryset"] = related_model.objects.filter(enterprise=request.tenant)
        return super().formfield_for_manytomany(db_field, request, **kwargs)


# ===========================================================================
# Domain Admin
# ===========================================================================

@admin.register(Domain)
class DomainAdmin(TenantBaseAdmin):
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
                if employee.role in ['founder', 'hr', 'supervisor']:
                    user.is_staff = True
                if employee.role == 'founder':
                    user.is_superuser = True
                user.save()
                employee.user = user
        if commit:
            employee.save()
        return employee


@admin.register(Employee)
class EmployeeAdmin(TenantBaseAdmin):
    form = EmployeeAdminForm
    list_display = (
        'employee_id', 'name', 'role', 'supervisor', 'domain', 'designation',
        'employment_type', 'email', 'is_active', 'date_joined',
    )
    list_display_links = ('employee_id', 'name')
    list_filter = ('role', 'domain', 'employment_type', 'gender', 'is_active')
    search_fields = ('name', 'employee_id', 'email', 'designation', 'phone')
    list_editable = ('is_active',)
    autocomplete_fields = ('domain', 'supervisor')
    raw_id_fields = ('user',)
    date_hierarchy = 'date_joined'
    ordering = ('name',)
    readonly_fields = ('created_at', 'updated_at', 'photo_preview')

    fieldsets = (
        ('User Account & Role', {
            'fields': ('custom_username', 'custom_password', 'user', 'role', 'supervisor'),
        }),
        ('Personal Details', {
            'fields': (
                'name', 'employee_id', 'gender', 'date_of_birth',
                'profile_photo', 'photo_preview',
            ),
        }),
        ('Role & Employment', {
            'fields': (
                'domain', 'designation', 'employment_type',
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
class MeetingAdmin(TenantBaseAdmin):
    list_display = (
        'title', 'domain', 'meeting_type', 'status_badge',
        'date', 'start_time', 'venue', 'attendee_count_display', 'organised_by',
    )
    list_display_links = ('title',)
    list_filter = ('status', 'meeting_type', 'domain', 'date')
    search_fields = ('title', 'venue', 'organised_by', 'agenda', 'minutes')
    filter_horizontal = ('attendees',)
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
class ProjectAdmin(TenantBaseAdmin):
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
class TaskAdmin(TenantBaseAdmin):
    list_display = ('title', 'project', 'display_assigned_to', 'due_date', 'status_badge', 'hours_logged')
    list_filter = ('status', 'project', 'assigned_to', 'due_date')
    search_fields = ('title', 'project__title', 'assigned_to__name')
    autocomplete_fields = ('project',)
    filter_horizontal = ('assigned_to',)
    ordering = ('due_date', 'title')
    readonly_fields = ('created_at', 'updated_at')

    def display_assigned_to(self, obj):
        return ", ".join([emp.name for emp in obj.assigned_to.all()])
    display_assigned_to.short_description = 'Assigned To'

    fieldsets = (
        ('Task details', {
            'fields': ('title', 'project', 'assigned_to', 'status', 'hours_logged'),
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
class TaskChecklistAdmin(TenantBaseAdmin):
    list_display = (
        'title', 'assigned_to', 'created_by', 'status_badge',
        'submitted_at', 'resolved_at', 'created_at',
    )
    list_filter = ('status', 'assigned_to__domain', 'created_at')
    search_fields = ('title', 'assigned_to__name', 'created_by__name', 'description')
    autocomplete_fields = ('assigned_to', 'created_by')
    ordering = ('-created_at',)
    readonly_fields = ('submitted_at', 'resolved_at', 'created_at', 'updated_at')

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
        from .models import EmployeeStats
        updated = queryset.update(
            status='COMPLETED',
            resolved_at=timezone.now(),
        )
        # Recalculate stats for all affected employees
        for item in queryset.select_related('assigned_to'):
            EmployeeStats.recalculate_for(item.assigned_to)
        self.message_user(request, f'{updated} item(s) marked as completed.')

    @admin.action(description='Reset selected items to Pending')
    def reset_to_pending(self, request, queryset):
        updated = queryset.update(
            status='PENDING',
            submitted_at=None,
            rejection_feedback='',
        )
        self.message_user(request, f'{updated} item(s) reset to Pending.')


# ===========================================================================
# EmployeeStats Admin  (read-only analytics view)
# ===========================================================================

@admin.register(EmployeeStats)
class EmployeeStatsAdmin(TenantBaseAdmin):
    list_display = (
        'employee', 'total_assigned', 'total_completed',
        'total_awaiting', 'total_pending',
        'completion_pct_display', 'last_recalculated',
    )
    list_filter  = ('employee__domain',)
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
            '<span style="color:{};font-weight:bold;">{:.1f}%</span>',
            colour, pct,
        )
