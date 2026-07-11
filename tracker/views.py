import base64
import csv
import io
import json

import matplotlib
matplotlib.use('Agg')  # Headless mode for matplotlib
import matplotlib.pyplot as plt
import pandas as pd

from django.conf import settings
from django.contrib.auth import login, get_user_model
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import models
from django.db.models import Count, Max, Q
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils import timezone

from .models import Domain, Employee, Meeting, Project, Task, TaskChecklist, EmployeeStats, Enterprise

CACHE_TTL_SECONDS = 300


from django.contrib.auth.views import LoginView
from django.utils.decorators import method_decorator
from functools import wraps

def ratelimit(key_prefix, limit, period):
    """
    Simple cache-based rate limiting decorator.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            # Client IP rate-limiting
            ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', '127.0.0.1'))
            ip = ip.split(',')[0].strip()
            cache_key = f"ratelimit:{key_prefix}:{ip}"
            
            requests = cache.get(cache_key, 0)
            if requests >= limit:
                return HttpResponse("Too Many Requests: Rate limit exceeded. Please try again later.", status=429)
            
            cache.set(cache_key, requests + 1, period)
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


@method_decorator(ratelimit(key_prefix='login', limit=5, period=60), name='dispatch')
class RateLimitedLoginView(LoginView):
    pass
@login_required
def dashboard_view(request):
    """Main analytics dashboard."""

    # --- Summary counts ---
    total_domains = Domain.objects.filter(enterprise=request.tenant, is_active=True).count()
    total_employees = Employee.objects.filter(enterprise=request.tenant, is_active=True).count()
    total_meetings = Meeting.objects.filter(enterprise=request.tenant).count()
    completed_meetings = Meeting.objects.filter(enterprise=request.tenant, status='completed').count()

    # --- Aggregation 1: meetings grouped by domain name ---
    by_domain_qs = (
        Meeting.objects.filter(enterprise=request.tenant)
        .values('domain__name')
        .annotate(total=Count('id'))
        .order_by('domain__name')
    )
    # Replace None (meetings with no domain) with a readable label
    by_domain = [
        {
            'label': row['domain__name'] or 'Unassigned',
            'total': row['total'],
        }
        for row in by_domain_qs
    ]

    # --- Aggregation 2: meetings grouped by intervention_scale ---
    by_scale_qs = (
        Meeting.objects.filter(enterprise=request.tenant)
        .values('intervention_scale')
        .annotate(total=Count('id'))
        .order_by('intervention_scale')
    )
    # Map raw key → human-readable label using the model's choices
    scale_labels = dict(Meeting._meta.get_field('intervention_scale').choices)
    by_scale = [
        {
            'label': scale_labels.get(row['intervention_scale'], row['intervention_scale']).title(),
            'total': row['total'],
        }
        for row in by_scale_qs
    ]

    # --- Recent meetings for the activity table ---
    recent_meetings = (
        Meeting.objects.filter(enterprise=request.tenant)
        .select_related('domain')
        .order_by('-date', '-start_time')[:10]
    )

    # Mask sensitive details for HR role
    recent_meetings = list(recent_meetings)
    profile = getattr(request.user, 'employee_profile', None)
    if profile and profile.role == 'hr':
        for m in recent_meetings:
            m.agenda = 'Confidential - Access Restricted'
            m.minutes = 'Confidential - Access Restricted'
            m.action_points = 'Confidential - Access Restricted'

    # Task Checklist dashboard integration
    awaiting_verification_count = 0
    personal_checklist_stats = None
    role = 'founder' if request.user.is_superuser else getattr(profile, 'role', 'employee')

    # Subordinate verification counts for supervisors, founders, and HR
    if role in ('founder', 'hr', 'supervisor'):
        if role == 'supervisor' and profile:
            subordinate_ids = list(
                Employee.objects.filter(enterprise=request.tenant, supervisor=profile).values_list('id', flat=True)
            )
            awaiting_verification_count = TaskChecklist.objects.filter(
                enterprise=request.tenant, assigned_to__id__in=subordinate_ids, status='AWAITING_VERIFICATION'
            ).count()
        else:
            # founder/hr/superuser can verify all
            awaiting_verification_count = TaskChecklist.objects.filter(
                enterprise=request.tenant, status='AWAITING_VERIFICATION'
            ).count()

    # Personal checklist progress snapshot
    if profile:
        stats_row = EmployeeStats.objects.filter(employee=profile).first()
        if stats_row:
            personal_checklist_stats = {
                'total': stats_row.total_assigned,
                'completed': stats_row.total_completed,
                'pending': stats_row.total_pending,
                'awaiting': stats_row.total_awaiting,
                'percentage': float(stats_row.completion_percentage),
            }
        else:
            personal_items = TaskChecklist.objects.filter(enterprise=request.tenant, assigned_to=profile)
            p_total = personal_items.count()
            if p_total > 0:
                p_comp = personal_items.filter(status='COMPLETED').count()
                p_await = personal_items.filter(status='AWAITING_VERIFICATION').count()
                p_pend = personal_items.filter(status='PENDING').count()
                personal_checklist_stats = {
                    'total': p_total,
                    'completed': p_comp,
                    'pending': p_pend,
                    'awaiting': p_await,
                    'percentage': round((p_comp / p_total) * 100, 2),
                }

    context = {
        # Summary cards
        'total_domains': total_domains,
        'total_employees': total_employees,
        'total_meetings': total_meetings,
        'completed_meetings': completed_meetings,
        # Chart data serialised to JSON so the template can embed it safely
        'by_domain_json': json.dumps(by_domain),
        'by_scale_json': json.dumps(by_scale),
        # Activity table
        'recent_meetings': recent_meetings,
        # Checklist stats
        'awaiting_verification_count': awaiting_verification_count,
        'personal_checklist_stats': personal_checklist_stats,
        'user_role': role,
        'generated_at': timezone.now(),
    }
    return render(request, 'tracker/dashboard.html', context)


@login_required
def export_meetings_csv(request):
    """Stream all meetings as a CSV download for founder reporting."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="meetings_export.csv"'

    writer = csv.writer(response)
    writer.writerow(['Title', 'Date', 'Domain', 'Intervention Scale', 'Type', 'Status', 'Venue', 'Organised By'])

    meetings = (
        Meeting.objects.filter(enterprise=request.tenant)
        .select_related('domain')
        .order_by('-date', '-start_time')
    )

    scale_labels = dict(Meeting._meta.get_field('intervention_scale').choices)
    type_labels = dict(Meeting._meta.get_field('meeting_type').choices)
    status_labels = dict(Meeting._meta.get_field('status').choices)

    for m in meetings:
        writer.writerow([
            m.title,
            m.date.strftime('%Y-%m-%d') if m.date else '',
            m.domain.name if m.domain else 'Unassigned',
            scale_labels.get(m.intervention_scale, m.intervention_scale),
            type_labels.get(m.meeting_type, m.meeting_type),
            status_labels.get(m.status, m.status),
            m.venue,
            m.organised_by,
        ])

    return response


@login_required
def domains_list_view(request):
    """List all domains. Active employee count resolved via annotation to avoid N+1."""
    domains = (
        Domain.objects.filter(enterprise=request.tenant)
        .annotate(emp_count=Count('employees', filter=models.Q(employees__is_active=True)))
        .order_by('name')
    )
    context = {
        'domains': domains,
        'generated_at': timezone.now(),
    }
    return render(request, 'domains.html', context)


@login_required
def employees_list_view(request):
    """List employees with optional filtering by name, domain, and designation."""
    from .filters import EmployeeFilter

    qs = (
        Employee.objects.filter(enterprise=request.tenant)
        .select_related('domain')
        .order_by('name')
    )
    employee_filter = EmployeeFilter(request.GET, queryset=qs)
    context = {
        'filter': employee_filter,
        'employees': employee_filter.qs,
        'generated_at': timezone.now(),
    }
    return render(request, 'employees.html', context)


@login_required
def meetings_list_view(request):
    """List meetings with optional filtering by title, domain, scale, and status."""
    from .filters import MeetingFilter

    qs = (
        Meeting.objects.filter(enterprise=request.tenant)
        .select_related('domain')
        .prefetch_related('attendees')
        .order_by('-date', '-start_time')
    )
    meeting_filter = MeetingFilter(request.GET, queryset=qs)
    meetings = list(meeting_filter.qs)

    # Mask sensitive details for HR role
    profile = getattr(request.user, 'employee_profile', None)
    if profile and profile.role == 'hr':
        for m in meetings:
            m.agenda = 'Confidential - Access Restricted'
            m.minutes = 'Confidential - Access Restricted'
            m.action_points = 'Confidential - Access Restricted'

    context = {
        'filter': meeting_filter,
        'meetings': meetings,
        'generated_at': timezone.now(),
    }
    return render(request, 'meetings.html', context)


@login_required
def policy_analytics_view(request):
    """View to analyze policy intervention scales using Pandas and Chart.js with caching."""
    # Organization-wide analytics cached using aggregate meeting count and latest update token
    meetings_count = Meeting.objects.filter(enterprise=request.tenant).count()
    latest_meeting = Meeting.objects.filter(enterprise=request.tenant).aggregate(latest=Max('updated_at'))['latest']
    latest_token = latest_meeting.isoformat() if latest_meeting else 'none'
    cache_key = f"policy_analytics:{request.tenant.subdomain}:{meetings_count}:{latest_token}"
    
    context = cache.get(cache_key)
    if context is not None:
        return render(request, 'analytics.html', context)
        
    # Query meetings (select_related for domain optimization)
    meetings_qs = Meeting.objects.filter(enterprise=request.tenant).select_related('domain').values(
        'intervention_scale', 'domain__name'
    )
    
    # Load into a Pandas DataFrame
    df = pd.DataFrame(list(meetings_qs))
    
    if df.empty:
        chart_data_json = "{}"
        crosstab_html = "<p class='text-muted'>No data available for analysis.</p>"
    else:
        # Fill missing values if any domain is None
        df['domain__name'] = df['domain__name'].fillna('Unassigned')
        
        # Human-readable labels for intervention scales
        scale_labels = dict(Meeting._meta.get_field('intervention_scale').choices)
        df['intervention_scale_label'] = df['intervention_scale'].map(scale_labels).fillna(df['intervention_scale'])
        
        # Generate crosstab: intervention_scale vs domain__name
        crosstab = pd.crosstab(df['intervention_scale_label'], df['domain__name'])
        
        # Reindex to ensure correct choice ordering on the chart and table
        scale_choices = Meeting._meta.get_field('intervention_scale').choices
        scale_display_names = [choice[1] for choice in scale_choices]
        crosstab = crosstab.reindex(scale_display_names, fill_value=0)
        
        # Render crosstab to HTML table with clean Bootstrap classes
        crosstab_html = crosstab.to_html(classes='table table-borderless table-hover table-sm align-middle mb-0')
        
        # ── Premium palette for domains ──
        PREMIUM_PALETTE = [
            '#2563eb', '#0891b2', '#0d9488', '#7c3aed',
            '#db2777', '#ea580c', '#65a30d', '#ca8a04',
        ]
        
        # Build datasets list for Chart.js
        chart_datasets = []
        for idx, col_name in enumerate(crosstab.columns):
            chart_datasets.append({
                'label': col_name,
                'data': [int(val) for val in crosstab[col_name]],
                'backgroundColor': PREMIUM_PALETTE[idx % len(PREMIUM_PALETTE)],
                'borderRadius': 4,
            })
            
        chart_data = {
            'labels': scale_display_names,
            'datasets': chart_datasets
        }
        chart_data_json = json.dumps(chart_data)
        
    context = {
        'chart_data_json': chart_data_json,
        'crosstab_html': crosstab_html,
        'generated_at': timezone.now(),
    }
    
    cache.set(cache_key, context, CACHE_TTL_SECONDS)
    return render(request, 'analytics.html', context)


@login_required
def employee_performance_view(request):
    """View to analyze employee workloads and task efficiency using Chart.js with caching and prefetch."""
    profile = getattr(request.user, 'employee_profile', None)
    role = 'founder' if request.user.is_superuser else 'employee'
    if profile:
        role = profile.role

    # Generate a secure cache fingerprint incorporating:
    # 1. User role & ID (for Row-Level Security)
    # 2. Total active tasks & latest update
    # 3. Total active projects & latest update
    tasks_count = Task.objects.filter(enterprise=request.tenant).count()
    latest_task_update = Task.objects.filter(enterprise=request.tenant).aggregate(latest=Max('updated_at'))['latest']
    latest_task_token = latest_task_update.isoformat() if latest_task_update else 'none'
    
    projects_count = Project.objects.filter(enterprise=request.tenant).count()
    latest_proj_update = Project.objects.filter(enterprise=request.tenant).aggregate(latest=Max('updated_at'))['latest']
    latest_proj_token = latest_proj_update.isoformat() if latest_proj_update else 'none'
    
    cache_key = (
        f"emp_perf:{request.tenant.subdomain}:{role}:{request.user.id}:"
        f"{tasks_count}:{latest_task_token}:"
        f"{projects_count}:{latest_proj_token}"
    )
    
    context = cache.get(cache_key)
    if context is not None:
        return render(request, 'employee_analytics.html', context)

    # Enforce Row-Level Security: Filter base querysets based on role and scope to request.tenant
    if role in ['founder', 'hr']:
        tasks_qs = Task.objects.filter(enterprise=request.tenant)
        employees_base_qs = Employee.objects.filter(enterprise=request.tenant, is_active=True)
    elif role == 'supervisor':
        tasks_qs = Task.objects.filter(enterprise=request.tenant, assigned_to__supervisor=profile)
        employees_base_qs = Employee.objects.filter(enterprise=request.tenant, supervisor=profile, is_active=True)
    else:
        allowed_ids = [profile.id] if profile else []
        tasks_qs = Task.objects.filter(enterprise=request.tenant, assigned_to__in=allowed_ids)
        employees_base_qs = Employee.objects.filter(enterprise=request.tenant, id__in=allowed_ids, is_active=True)

    # 1. Workload Chart: Active tasks per employee
    from django.db.models import Count, Q
    
    # Run aggregation for workload chart counts
    emp_workloads = (
        employees_base_qs
        .annotate(active_tasks_count=Count('tasks', filter=Q(tasks__status__in=['pending', 'in_progress'])))
        .filter(active_tasks_count__gt=0)
        .order_by('-active_tasks_count')
    )
    
    workload_labels = [emp.name for emp in emp_workloads]
    workload_counts = [emp.active_tasks_count for emp in emp_workloads]
    workload_json = json.dumps({
        'labels': workload_labels,
        'data': workload_counts
    })

    # 2. Efficiency Chart: Completed vs Overdue
    completed_count = tasks_qs.filter(status='completed').count()
    overdue_count = tasks_qs.filter(status='overdue').count()
    
    efficiency_percentage = 0.0
    if completed_count + overdue_count > 0:
        efficiency_percentage = (completed_count / (completed_count + overdue_count)) * 100

    efficiency_json = json.dumps({
        'labels': ['Completed', 'Overdue'],
        'data': [completed_count, overdue_count]
    })

    # 3. Optimized Employee Registry Table Data (N+1 query resolution)
    # Prefetch led_projects and tasks to process them in-memory
    employees = (
        employees_base_qs
        .select_related('domain')
        .prefetch_related('led_projects', 'tasks')
        .order_by('name')
    )
    
    employees_data = []
    for emp in employees:
        # Resolve metrics in memory to prevent N+1 hits
        led_projects = list(emp.led_projects.all())
        emp_tasks = list(emp.tasks.all())
        
        active_projects_led = sum(1 for p in led_projects if p.status == 'active')
        active_tasks_count = sum(1 for t in emp_tasks if t.status in ['pending', 'in_progress'])
        
        # Deadlines in memory
        deadlines = []
        upcoming_tasks = [t for t in emp_tasks if t.status in ['pending', 'in_progress', 'overdue']]
        if upcoming_tasks:
            upcoming_tasks.sort(key=lambda x: x.due_date)
            nearest_task = upcoming_tasks[0]
            deadlines.append((nearest_task.due_date, f"Task: {nearest_task.title}"))
            
        upcoming_projects = [p for p in led_projects if p.status in ['planning', 'active']]
        if upcoming_projects:
            upcoming_projects.sort(key=lambda x: x.deadline)
            nearest_project = upcoming_projects[0]
            deadlines.append((nearest_project.deadline, f"Project: {nearest_project.title}"))
            
        if deadlines:
            deadlines.sort(key=lambda x: x[0])
            nearest_date, nearest_desc = deadlines[0]
            deadline_display = f"{nearest_date.strftime('%d %b %Y')} ({nearest_desc})"
        else:
            deadline_display = "No upcoming deadlines"
            
        employees_data.append({
            'employee': emp,
            'active_projects_led': active_projects_led,
            'active_tasks': active_tasks_count,
            'upcoming_deadline': deadline_display,
        })

    context = {
        'workload_json': workload_json,
        'efficiency_json': efficiency_json,
        'has_workload_data': len(workload_labels) > 0,
        'has_efficiency_data': (completed_count + overdue_count) > 0,
        'efficiency_percentage': round(efficiency_percentage, 1),
        'employees_data': employees_data,
        'generated_at': timezone.now(),
    }
    
    cache.set(cache_key, context, CACHE_TTL_SECONDS)
    return render(request, 'employee_analytics.html', context)







# ─────────────────────────────────────────────────────────────────────────────
# Dev Mode: Role Masquerade View
# ─────────────────────────────────────────────────────────────────────────────
#
# Maps human-friendly role slugs to Django usernames.
# Add / edit entries here to match the usernames in your local database.
#
DEV_ROLE_MAP = {
    'founder':    'admin',      # typically the superuser / founder account
    'hr':         'hr_user',    # a staff user with HR permissions
    'supervisor': 'supervisor', # a staff user with supervisor permissions
    'employee':   'employee',   # a regular non-staff user
}


@ratelimit(key_prefix='dev_switch', limit=10, period=60)
def dev_role_switch_view(request, role_name):
    """
    DEV-ONLY masquerade endpoint.
    Logs the current session in as a predefined test user for the given role,
    allowing rapid RBAC testing without re-entering passwords.

    Blocked in production: returns 403 when DEBUG=False.

    Usage:
        GET /dashboard/dev-switch/founder/    → log in as the 'admin' user
        GET /dashboard/dev-switch/hr/         → log in as 'hr_user'
        GET /dashboard/dev-switch/supervisor/ → log in as 'supervisor'
        GET /dashboard/dev-switch/employee/   → log in as 'employee'

    To add roles: extend DEV_ROLE_MAP above with 'slug': 'django_username'.
    """
    # Hard block in production – this view must never be reachable on live servers
    if not settings.DEBUG:
        return HttpResponseForbidden(
            '<h1>403 Forbidden</h1>'
            '<p>The Dev Role Switcher is disabled outside of DEBUG mode.</p>'
        )

    User = get_user_model()

    username = DEV_ROLE_MAP.get(role_name.lower())
    if not username:
        from django.http import HttpResponseBadRequest
        return HttpResponseBadRequest(
            f'Unknown role "{role_name}". '
            f'Available roles: {", ".join(DEV_ROLE_MAP.keys())}'
        )

    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        from django.contrib import messages
        messages.warning(
            request,
            f'Dev switcher: no user with username "{username}" exists. '
            f'Create it via manage.py createsuperuser or the admin panel.'
        )
        return redirect('tracker:dashboard')

    # Dev Switcher Patch: Ensure the user has an Employee profile with the correct role
    if not hasattr(user, 'employee_profile'):
        from .models import Employee
        import random
        rand_suffix = random.randint(1000, 9999)
        Employee.objects.create(
            enterprise=request.tenant,
            user=user,
            employee_id=f"DEV-{user.username.upper()}-{rand_suffix}"[:30],
            name=user.username.title(),
            email=user.email or f"{user.username}_{rand_suffix}@cysd.org",
            role=role_name.lower(),
            designation="Dev Masquerade Profile",
            is_active=True,
        )
    else:
        profile = user.employee_profile
        if profile.role != role_name.lower():
            profile.role = role_name.lower()
            profile.save()

    # Django's login() requires a backend attribute when called outside of
    # the standard authenticate() flow – set it explicitly.
    user.backend = 'django.contrib.auth.backends.ModelBackend'
    login(request, user)

    from django.contrib import messages
    messages.success(
        request,
        f'[Dev] Switched to role "{role_name}" → logged in as '
        f'<strong>{user.username}</strong>.'
    )
    return redirect('tracker:dashboard')


@login_required
def my_tasks_view(request):
    """Personal dashboard view for employees to track their assigned tasks."""
    profile = getattr(request.user, 'employee_profile', None)
    if not profile:
        from django.contrib import messages
        messages.warning(request, "You do not have an Employee profile linked to your account.")
        return redirect('tracker:dashboard')

    # Get all tasks assigned to this employee
    tasks = Task.objects.filter(enterprise=request.tenant, assigned_to=profile).select_related('project').order_by('due_date')

    # Calculate summary statistics for standard tasks
    total_tasks = tasks.count()
    pending_tasks = tasks.filter(status='pending').count()
    in_progress_tasks = tasks.filter(status='in_progress').count()
    completed_tasks = tasks.filter(status='completed').count()
    overdue_tasks = tasks.filter(status='overdue').count()
    
    # Calculate total hours logged
    total_hours = sum(t.hours_logged for t in tasks)

    # Get checklist items assigned to this employee
    checklists = TaskChecklist.objects.filter(enterprise=request.tenant, assigned_to=profile).select_related('created_by').order_by('-created_at')
    unchecked_checklists = checklists.filter(status='PENDING')
    awaiting_checklists = checklists.filter(status='AWAITING_VERIFICATION')
    completed_checklists = checklists.filter(status='COMPLETED')

    # Combined Stats (Tasks + Checklist items)
    comb_total = total_tasks + checklists.count()
    comb_completed = completed_tasks + completed_checklists.count()
    comb_pending = pending_tasks + in_progress_tasks + unchecked_checklists.count()
    comb_awaiting = awaiting_checklists.count()
    comb_overdue = overdue_tasks
    
    pct = round((comb_completed / comb_total) * 100) if comb_total > 0 else 0

    # Combine standard tasks and checklist items into a single list
    unified_list = []
    
    # Add standard tasks
    for t in tasks:
        unified_list.append({
            'is_checklist': False,
            'id': t.id,
            'title': t.title,
            'description': '',
            'project_title': t.project.title,
            'date_label': 'Due Date',
            'date': t.due_date,
            'status': t.status,  # pending, in_progress, completed, overdue
            'hours_logged': f"{t.hours_logged} hrs",
            'creator': None,
        })
        
    # Add checklist items
    status_map = {
        'PENDING': 'pending',
        'AWAITING_VERIFICATION': 'awaiting_verification',
        'COMPLETED': 'completed',
    }
    for item in checklists:
        unified_list.append({
            'is_checklist': True,
            'id': item.id,
            'title': item.title,
            'description': item.description,
            'project_title': 'Checklist Item',
            'date_label': 'Created Date',
            'date': item.created_at.date() if item.created_at else timezone.now().date(),
            'status': status_map.get(item.status, 'pending'),
            'hours_logged': '—',
            'creator': item.created_by.name if item.created_by else 'System',
        })
        
    # Sort unified list: active/pending items first, completed items at the bottom
    def sort_key(x):
        is_completed = 1 if x['status'] == 'completed' else 0
        date_val = x['date'] or timezone.now().date()
        return (is_completed, date_val)
        
    unified_list.sort(key=sort_key)

    context = {
        'profile': profile,
        'unified_list': unified_list,
        
        # Combined stats for dashboard counters and progress bar
        'total_tasks': comb_total,
        'completed_tasks': comb_completed,
        'pending_tasks': comb_pending,
        'awaiting_tasks': comb_awaiting,
        'overdue_tasks': comb_overdue,
        'total_hours': total_hours,
        'pct': pct,
    }
    return render(request, 'my_tasks.html', context)


# =============================================================================
# Task Checklist Views
# =============================================================================


@login_required
def checklist_submit_view(request, item_id):
    """
    Phase 1 Action — Employee submits a PENDING item for supervisor review.
    Transitions: PENDING → AWAITING_VERIFICATION.
    Only the assigned employee can trigger this.
    """
    from django.db import transaction
    from django.contrib import messages

    profile = getattr(request.user, 'employee_profile', None)
    if not profile:
        return HttpResponseForbidden("No employee profile found.")

    if request.method != 'POST':
        return HttpResponseForbidden("POST required.")

    try:
        with transaction.atomic():
            item = TaskChecklist.objects.select_for_update().get(
                pk=item_id, assigned_to=profile
            )
            if item.status != 'PENDING':
                messages.warning(request, "Only PENDING items can be submitted for verification.")
                return redirect('tracker:checklist_employee')

            item.status = 'AWAITING_VERIFICATION'
            item.submitted_at = timezone.now()
            # Bypass full_clean for status transitions — integrity is enforced at creation
            TaskChecklist.objects.filter(pk=item.pk).update(
                status='AWAITING_VERIFICATION',
                submitted_at=item.submitted_at,
            )
    except TaskChecklist.DoesNotExist:
        messages.error(request, "Checklist item not found or not assigned to you.")
        return redirect('tracker:checklist_employee')

    messages.success(request, f'"{item.title}" submitted for supervisor verification.')
    return redirect('tracker:checklist_employee')


@login_required
def checklist_supervisor_view(request):
    """
    Phase 2 — Supervisor Verification Center.

    Shows:
      • Items awaiting verification from any of the supervisor's direct reports.
      • All items across the team (for full visibility), grouped by status.

    Accessible by supervisor, hr, and founder only.
    """
    profile = getattr(request.user, 'employee_profile', None)
    role = 'founder' if request.user.is_superuser else getattr(profile, 'role', 'employee')

    if role not in ('founder', 'hr', 'supervisor'):
        return HttpResponseForbidden("You do not have permission to access the verification center.")

    if role == 'supervisor':
        subordinate_ids = list(
            Employee.objects.filter(enterprise=request.tenant, supervisor=profile).values_list('id', flat=True)
        )
        base_qs = TaskChecklist.objects.filter(enterprise=request.tenant, assigned_to__id__in=subordinate_ids)
    else:
        # founder / hr see the entire organization (scoped to tenant)
        base_qs = TaskChecklist.objects.filter(enterprise=request.tenant)

    awaiting_items = (
        base_qs
        .filter(status='AWAITING_VERIFICATION')
        .select_related('assigned_to', 'created_by')
        .order_by('submitted_at')
    )
    all_items = (
        base_qs
        .select_related('assigned_to', 'created_by')
        .order_by('assigned_to__name', 'status', '-created_at')
    )

    # Per-employee stats snapshot for the summary cards
    if role == 'supervisor':
        team_employees = Employee.objects.filter(
            enterprise=request.tenant, supervisor=profile, is_active=True
        ).prefetch_related('stats')
    else:
        team_employees = Employee.objects.filter(enterprise=request.tenant, is_active=True).prefetch_related('stats')

    context = {
        'awaiting_items':  awaiting_items,
        'awaiting_count':  awaiting_items.count(),
        'all_items':       all_items,
        'team_employees':  team_employees,
        'profile':         profile,
        'role':            role,
    }
    return render(request, 'checklist_supervisor.html', context)


@login_required
def checklist_resolve_view(request, item_id):
    """
    Phase 3 — Supervisor approves or rejects an AWAITING_VERIFICATION item.

    POST params:
        action  – 'approve' | 'reject'
        feedback – (optional) rejection note

    Approve: AWAITING_VERIFICATION → COMPLETED  (triggers signal → EmployeeStats update)
    Reject:  AWAITING_VERIFICATION → PENDING    (clears timestamps, stores feedback)
    """
    from django.db import transaction
    from django.contrib import messages

    profile = getattr(request.user, 'employee_profile', None)
    role = 'founder' if request.user.is_superuser else getattr(profile, 'role', 'employee')

    if role not in ('founder', 'hr', 'supervisor'):
        return HttpResponseForbidden("Only supervisors or above can resolve checklist items.")

    if request.method != 'POST':
        return HttpResponseForbidden("POST required.")

    action   = request.POST.get('action', '').strip()
    feedback = request.POST.get('feedback', '').strip()

    if action not in ('approve', 'reject'):
        messages.error(request, "Invalid action. Must be 'approve' or 'reject'.")
        return redirect('tracker:checklist_supervisor')

    try:
        with transaction.atomic():
            item = TaskChecklist.objects.select_for_update().get(pk=item_id)

            # Supervisors can only resolve items belonging to their own subordinates
            if role == 'supervisor' and item.assigned_to.supervisor_id != profile.pk:
                return HttpResponseForbidden("You can only resolve items assigned to your direct reports.")

            if item.status != 'AWAITING_VERIFICATION':
                messages.warning(request, "Only items awaiting verification can be resolved.")
                return redirect('tracker:checklist_supervisor')

            now = timezone.now()
            if action == 'approve':
                # Use queryset update to bypass full_clean (status transitions are
                # controlled here, not user-facing form submissions)
                TaskChecklist.objects.filter(pk=item.pk).update(
                    status='COMPLETED',
                    rejection_feedback='',
                    resolved_at=now,
                )
                # Manually trigger stats update since queryset.update() skips signals
                item.refresh_from_db()
                EmployeeStats.recalculate_for(item.assigned_to)
                messages.success(
                    request,
                    f'✅ "{item.title}" approved. '
                    f'{item.assigned_to.name}\'s stats have been updated.'
                )
            else:
                TaskChecklist.objects.filter(pk=item.pk).update(
                    status='PENDING',
                    rejection_feedback=feedback,
                    submitted_at=None,
                    resolved_at=now,
                )
                # Also recalculate on rejection so pending counts stay accurate
                EmployeeStats.recalculate_for(item.assigned_to)
                messages.warning(
                    request,
                    f'🔁 "{item.title}" returned to {item.assigned_to.name} for revision.'
                )
    except TaskChecklist.DoesNotExist:
        messages.error(request, "Checklist item not found.")
        return redirect('tracker:checklist_supervisor')

    return redirect('tracker:checklist_supervisor')


@login_required
def setup_organization_view(request):
    """
    Onboarding/setup view for the Enterprise ERP Manager/Superuser.
    Allows editing details of the current tenant (Enterprise).
    """
    from django.contrib import messages
    from .forms import EnterpriseForm
    
    profile_role = getattr(request.user, 'employee_profile', None)
    is_authorized = request.user.is_superuser or (profile_role and profile_role.role in ('founder', 'hr'))
    
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return redirect('tracker:dashboard')
        
    if not is_authorized:
        return render(request, 'tracker/setup_organization.html', {
            'profile': tenant,
            'is_authorized': False,
        })
    
    if request.method == 'POST':
        form = EnterpriseForm(request.POST, request.FILES, instance=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, "Enterprise settings updated successfully!")
            return redirect('tracker:dashboard')
    else:
        form = EnterpriseForm(instance=tenant)
        
    return render(request, 'tracker/setup_organization.html', {
        'form': form,
        'profile': tenant,
        'is_authorized': True,
    })



