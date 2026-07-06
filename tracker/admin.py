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
from unfold.admin import ModelAdmin, TabularInline
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import Domain, Employee, Meeting, Project, Task


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
class EmployeeAdmin(ModelAdmin):
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
class MeetingAdmin(ModelAdmin):
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
    list_display = ('title', 'project', 'assigned_to', 'due_date', 'status_badge', 'hours_logged')
    list_filter = ('status', 'project', 'assigned_to', 'due_date')
    search_fields = ('title', 'project__title', 'assigned_to__name')
    autocomplete_fields = ('project', 'assigned_to')
    ordering = ('due_date', 'title')
    readonly_fields = ('created_at', 'updated_at')

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
