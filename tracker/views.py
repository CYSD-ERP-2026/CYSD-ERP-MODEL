import csv
import json

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils import timezone

from .models import (
    Domain,
    Employee,
    EmployeeStats,
    Meeting,
    Task,
    TaskChecklist,
)

CACHE_TTL_SECONDS = 300


from functools import wraps

from django.contrib.auth.views import LoginView
from django.utils.decorators import method_decorator


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


@method_decorator(ratelimit(key_prefix='login', limit=10, period=60), name='dispatch')
class RateLimitedLoginView(LoginView):
    pass
@login_required
def dashboard_view(request: HttpRequest) -> HttpResponse:
    """Main analytics dashboard."""

    # --- Summary counts ---
    total_domains = Domain.objects.filter(is_active=True).count()
    total_employees = Employee.objects.filter(is_active=True).count()
    total_meetings = Meeting.objects.filter().count()
    completed_meetings = Meeting.objects.filter(status='completed').count()

    # --- Aggregation 1: meetings grouped by domain name ---
    by_domain_qs = (
        Meeting.objects.filter()
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
        Meeting.objects.filter()
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
        Meeting.objects.filter()
        .select_related('domain')
        .order_by('-date', '-start_time')[:10]
    )

    # Mask sensitive details based on permission (replaces HR role check)
    recent_meetings = list(recent_meetings)
    profile = getattr(request.user, 'employee_profile', None)
    if profile:
        perms = getattr(profile, 'permissions', None)
        if not perms or not perms.can_read_confidential_meetings:
            for m in recent_meetings:
                m.agenda = 'Confidential - Access Restricted'
                m.minutes = 'Confidential - Access Restricted'
                m.action_points = 'Confidential - Access Restricted'

    # Task Checklist dashboard integration
    awaiting_verification_count = 0
    personal_checklist_stats = None

    # Subordinate verification counts based on checklist_approve_scope
    if profile:
        perms = getattr(profile, 'permissions', None)
        if perms and perms.can_approve_checklist_items:
            if perms.checklist_approve_scope == 'own_team':
                subordinate_ids = list(
                    Employee.objects.filter(supervisor=profile).values_list('id', flat=True)
                )
                awaiting_verification_count = TaskChecklist.objects.filter(
                    assigned_to__id__in=subordinate_ids, status='AWAITING_VERIFICATION'
                ).count()
            elif perms.checklist_approve_scope == 'all':
                awaiting_verification_count = TaskChecklist.objects.filter(
                    status='AWAITING_VERIFICATION'
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
            personal_items = TaskChecklist.objects.filter(assigned_to=profile)
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
        'generated_at': timezone.now(),
    }
    return render(request, 'tracker/dashboard.html', context)


@login_required
def export_meetings_csv(request):
    """Stream all meetings as a CSV download for founder reporting."""
    profile = getattr(request.user, 'employee_profile', None)
    perms = getattr(profile, 'permissions', None) if profile else None

    if not perms or not (perms.can_read_confidential_meetings or getattr(perms, 'can_manage_organization', False)):
        return HttpResponseForbidden("You do not have permission to export meetings.")

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="meetings_export.csv"'

    writer = csv.writer(response)
    writer.writerow(['Title', 'Date', 'Domain', 'Intervention Scale', 'Type', 'Status', 'Venue', 'Organised By'])

    meetings = (
        Meeting.objects.filter()
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
        Domain.objects.filter()
        .annotate(emp_count=Count('employees', filter=Q(employees__is_active=True)))
        .order_by('name')
    )
    context = {
        'domains': domains,
    }
    return render(request, 'domains.html', context)


@login_required
def employees_list_view(request):
    """List employees with optional filtering by name, domain, and designation."""
    from .filters import EmployeeFilter

    qs = (
        Employee.objects.filter()
        .select_related('domain')
        .order_by('name')
    )
    employee_filter = EmployeeFilter(request.GET, queryset=qs, request=request)
    profile = getattr(request.user, 'employee_profile', None)
    perms = getattr(profile, 'permissions', None) if profile else None

    context = {
        'filter': employee_filter,
        'employees': employee_filter.qs,
        'can_manage_employees': getattr(perms, 'can_manage_employees', False) if perms else False,
    }
    return render(request, 'employees.html', context)

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from .models import EmployeePermission


@login_required
@ratelimit(key_prefix='update_perms', limit=10, period=60)
@require_http_methods(["PATCH"])
def update_employee_permissions(request, emp_id):
    caller_profile = getattr(request.user, 'employee_profile', None)
    if not caller_profile:
        return JsonResponse({'error': 'You must be an employee to do this.'}, status=403)

    caller_perms = getattr(caller_profile, 'permissions', None)
    if not caller_perms or not caller_perms.can_manage_employees:
        return JsonResponse({'error': 'You do not have permission to manage employees.'}, status=403)

    target_employee = get_object_or_404(Employee, id=emp_id)
    target_perms = getattr(target_employee, 'permissions', None)
    if not target_perms:
        target_perms = EmployeePermission.objects.create(employee=target_employee)

    try:
        data = json.loads(request.body)

        allowed_fields = [
            'can_manage_employees',
            'can_manage_organization',
            'can_assign_checklist_items',
            'can_approve_checklist_items',
            'can_read_confidential_meetings',
            'can_access_admin_panel',
            'can_self_assign_tasks',
            'can_view_employee_analytics',
            'checklist_assign_scope',
            'checklist_approve_scope',
            'employee_analytics_scope',
        ]

        for field in allowed_fields:
            if field in data:
                if field in ['checklist_assign_scope', 'checklist_approve_scope', 'employee_analytics_scope']:
                    if data[field] not in ['none', 'own_team', 'all']:
                        return JsonResponse({'error': f'Invalid value for {field}.'}, status=400)
                setattr(target_perms, field, data[field])

        target_perms.save()
        return JsonResponse({'success': True})
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data.'}, status=400)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error updating permissions: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal server error occurred.'}, status=500)


@login_required
def meetings_list_view(request):
    """List meetings with optional filtering by title, domain, scale, and status."""
    from .filters import MeetingFilter

    profile = getattr(request.user, 'employee_profile', None)
    perms = getattr(profile, 'permissions', None) if profile else None

    qs = (
        Meeting.objects.filter()
        .select_related('domain')
        .prefetch_related('attendees')
        .order_by('-date', '-start_time')
    )

    # Filter meetings visibility: Only Superusers and those who can manage organization (Founder/Admin)
    # can see all meetings. Others can only see meetings they are attending.
    can_see_all_meetings = request.user.is_superuser or (perms and perms.can_manage_organization)

    if not can_see_all_meetings and profile:
        qs = qs.filter(attendees=profile).distinct()

    meeting_filter = MeetingFilter(request.GET, queryset=qs, request=request)
    meetings = list(meeting_filter.qs)

    # Mask sensitive details based on permission (replaces HR role check)
    profile = getattr(request.user, 'employee_profile', None)
    if profile:
        perms = getattr(profile, 'permissions', None)
        if not perms or not perms.can_read_confidential_meetings:
            for m in meetings:
                m.agenda = 'Confidential - Access Restricted'
                m.minutes = 'Confidential - Access Restricted'
                m.action_points = 'Confidential - Access Restricted'

    # Check if user has permission to create meetings (Supervisor and above)
    can_create_meeting = False
    if profile and perms:
        # We consider Supervisor and above to be those who can approve or assign checklist items
        # or manage organization
        can_create_meeting = perms.can_assign_checklist_items or perms.can_manage_organization

    context = {
        'filter': meeting_filter,
        'meetings': meetings,
        'can_create_meeting': can_create_meeting,
        'domains': Domain.objects.filter(is_active=True) if can_create_meeting else [],
        'all_employees': Employee.objects.filter(is_active=True).order_by('name') if can_create_meeting else [],
    }
    return render(request, 'meetings.html', context)

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
        import random

        from .models import Employee
        rand_suffix = random.randint(1000, 9999)
        Employee.objects.create(
            user=user,
            employee_id=f"DEV-{user.username.upper()}-{rand_suffix}"[:30],
            name=user.username.title(),
            email=user.email or f"{user.username}_{rand_suffix}@cysd.org",
            designation="Dev Masquerade Profile",
            is_active=True)
    else:
        pass  # profile already exists, nothing to do

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
    tasks = Task.objects.filter(assigned_to=profile).select_related('project').order_by('due_date')

    # Calculate summary statistics for standard tasks
    total_tasks = tasks.count()
    pending_tasks = tasks.filter(status='pending').count()
    in_progress_tasks = tasks.filter(status='in_progress').count()
    completed_tasks = tasks.filter(status='completed').count()
    overdue_tasks = tasks.filter(status='overdue').count()

    # Get checklist items assigned to this employee
    checklists = TaskChecklist.objects.filter(assigned_to=profile).select_related('created_by').order_by('-created_at')
    unchecked_checklists = checklists.filter(status='PENDING')
    awaiting_checklists = checklists.filter(status='AWAITING_VERIFICATION')
    completed_checklists = checklists.filter(status='COMPLETED')

    # Combined Stats (Tasks + Checklist items)
    comb_total = total_tasks + checklists.count()
    comb_completed = completed_tasks + completed_checklists.count()
    comb_pending = pending_tasks + in_progress_tasks + unchecked_checklists.count()
    comb_awaiting = awaiting_checklists.count()
    comb_overdue = overdue_tasks
    self_allocated_count = checklists.filter(is_self_allocated=True).count()

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
            'creator': item.created_by.name if item.created_by else 'System',
            'is_self_allocated': item.is_self_allocated,
            'rejection_feedback': item.rejection_feedback,
        })

    # Sort unified list: active/pending items first, completed items at the bottom
    def sort_key(x):
        is_completed = 1 if x['status'] == 'completed' else 0
        date_val = x['date'] or timezone.now().date()
        return (is_completed, date_val)

    unified_list.sort(key=sort_key)

    from datetime import timedelta
    today = timezone.now().date()
    end_of_week = today + timedelta(days=7)

    from .models import Meeting
    meetings_this_week = Meeting.objects.filter(
        attendees=profile,
        date__range=[today, end_of_week]
    ).order_by('date', 'start_time')

    context = {
        'profile': profile,
        'unified_list': unified_list,

        # Combined stats for dashboard counters and progress bar
        'total_tasks': comb_total,
        'completed_tasks': comb_completed,
        'pending_tasks': comb_pending,
        'awaiting_tasks': comb_awaiting,
        'overdue_tasks': comb_overdue,
        'self_allocated_count': self_allocated_count,
        'pct': pct,

        'meetings_this_week': meetings_this_week,
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
    from django.contrib import messages
    from django.db import transaction

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
                submitted_at=item.submitted_at)
    except TaskChecklist.DoesNotExist:
        from django.http import Http404
        raise Http404("Checklist item not found or not assigned to you.")

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
    perms = getattr(profile, 'permissions', None) if profile else None

    if not perms or not perms.can_approve_checklist_items:
        return HttpResponseForbidden("You do not have permission to access the verification center.")

    # Determine data scope from checklist_approve_scope
    approve_scope = perms.checklist_approve_scope

    if approve_scope == 'own_team':
        subordinate_ids = list(
            Employee.objects.filter(supervisor=profile).values_list('id', flat=True)
        )
        base_qs = TaskChecklist.objects.filter(assigned_to__id__in=subordinate_ids)
    else:
        # scope == 'all' → see the entire organization (scoped to tenant)
        base_qs = TaskChecklist.objects.filter()

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
    if approve_scope == 'own_team':
        team_employees = Employee.objects.filter(
            supervisor=profile, is_active=True
        ).prefetch_related('stats')
    else:
        team_employees = Employee.objects.filter(is_active=True).prefetch_related('stats')

    # Preserve 'role' in context for template backwards-compat
    role = getattr(profile, 'role', 'employee')
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
    from django.contrib import messages
    from django.db import transaction

    profile = getattr(request.user, 'employee_profile', None)
    perms = getattr(profile, 'permissions', None) if profile else None

    if not perms or not perms.can_approve_checklist_items:
        return HttpResponseForbidden("Only employees with checklist approval permission can resolve items.")

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

            # Scope check: 'own_team' restricts to direct reports only
            if perms.checklist_approve_scope == 'own_team' and item.assigned_to.supervisor_id != profile.pk:
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
                    resolved_at=now)
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
                    resolved_at=now)
                # Also recalculate on rejection so pending counts stay accurate
                EmployeeStats.recalculate_for(item.assigned_to)
                messages.warning(
                    request,
                    f'🔁 "{item.title}" returned to {item.assigned_to.name} for revision.'
                )
    except TaskChecklist.DoesNotExist:
        from django.http import Http404
        raise Http404("Checklist item not found.")

    return redirect('tracker:checklist_supervisor')



@login_required
def checklist_create_view(request):
    """
    Phase 1 — Supervisor assigns a new checklist item directly from the frontend.
    """
    from django.contrib import messages
    from django.core.exceptions import ValidationError
    from django.http import HttpResponseForbidden
    from django.shortcuts import redirect

    from .models import Employee, TaskChecklist

    profile = getattr(request.user, 'employee_profile', None)
    perms = getattr(profile, 'permissions', None) if profile else None

    if not perms or not perms.can_assign_checklist_items:
        return HttpResponseForbidden("You do not have permission to assign checklist items.")

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        assigned_to_id = request.POST.get('assigned_to')

        if not title or not assigned_to_id:
            messages.error(request, "Title and assignee are required.")
            return redirect('tracker:checklist_supervisor')

        try:
            assigned_to = Employee.objects.get(pk=assigned_to_id)

            # Scope check
            if perms.checklist_assign_scope == 'own_team' and assigned_to.supervisor_id != profile.pk:
                messages.error(request, "You can only assign tasks to your direct reports.")
                return redirect('tracker:checklist_supervisor')

            try:
                TaskChecklist.objects.create(
                    title=title,
                    description=description,
                    assigned_to=assigned_to,
                    created_by=profile,
                    status='PENDING'
                )

                from tracker.models import EmployeeStats
                EmployeeStats.recalculate_for(assigned_to)

                messages.success(request, f"Task '{title}' assigned to {assigned_to.name} successfully.")
            except ValidationError as e:
                # Convert the error dict to a list of messages or a single string
                error_msg = " ".join([err for err_list in e.message_dict.values() for err in err_list]) if hasattr(e, 'message_dict') else str(e)
                messages.error(request, f"Validation Error: {error_msg}")
        except Employee.DoesNotExist:
            messages.error(request, "Invalid employee selected.")

    return redirect('tracker:checklist_supervisor')

@login_required
def meeting_create_view(request):
    """
    Creates a new meeting from the frontend.
    Restricted to supervisor and above.
    """

    from django.contrib import messages
    from django.http import HttpResponseForbidden
    from django.shortcuts import redirect

    from .models import Domain, Employee, Meeting

    profile = getattr(request.user, 'employee_profile', None)
    perms = getattr(profile, 'permissions', None) if profile else None

    # Restrict to supervisor and above (can_assign_checklist_items is a good proxy)
    if not perms or not (perms.can_assign_checklist_items or perms.can_manage_organization):
        return HttpResponseForbidden("You do not have permission to schedule meetings.")

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        domain_id = request.POST.get('domain')
        meeting_type = request.POST.get('meeting_type')
        intervention_scale = request.POST.get('intervention_scale')
        status = request.POST.get('status', 'scheduled')
        date_str = request.POST.get('date')
        start_time_str = request.POST.get('start_time')
        end_time_str = request.POST.get('end_time')
        venue = request.POST.get('venue', '').strip()
        agenda = request.POST.get('agenda', '').strip()
        attendee_ids = request.POST.getlist('attendees')

        if not title or not date_str:
            messages.error(request, "Title and Date are required.")
            return redirect('tracker:meetings')

        try:
            domain = Domain.objects.get(pk=domain_id) if domain_id else None

            # Create the meeting
            meeting = Meeting(
                title=title,
                domain=domain,
                meeting_type=meeting_type,
                intervention_scale=intervention_scale,
                status=status,
                date=date_str,
                venue=venue,
                agenda=agenda,
                organizer=profile,
                organised_by=profile.name if profile else request.user.username
            )

            if start_time_str:
                meeting.start_time = start_time_str
            if end_time_str:
                meeting.end_time = end_time_str

            meeting.save()

            # Add attendees
            if attendee_ids:
                attendees = Employee.objects.filter(id__in=attendee_ids)
                meeting.attendees.set(attendees)

            messages.success(request, f"Meeting '{title}' created successfully.")
        except Exception as e:
            messages.error(request, f"Failed to create meeting: {str(e)}")

    return redirect('tracker:meetings')


@login_required
def create_self_task(request):
    """
    Self-Task Allocation — Employee creates a checklist item assigned to themselves.

    This allows employees to proactively pick up work when seniors are busy.
    The task is flagged as `is_self_allocated=True` and follows the normal
    PENDING → AWAITING_VERIFICATION → COMPLETED lifecycle, routing through
    the Senior Verification Center for approval.

    Guards:
        1. can_self_assign_tasks permission must be True.
        2. profile.supervisor must be set — otherwise there is no supervisor
           to route the verification to, and the item would silently sit
           unreviewed.
    """
    from django.contrib import messages

    profile = getattr(request.user, 'employee_profile', None)
    if not profile:
        return HttpResponseForbidden("No employee profile found.")

    # ── Permission gate ──
    perms = getattr(profile, 'permissions', None)
    if not perms or not perms.can_self_assign_tasks:
        return HttpResponseForbidden(
            "You do not have permission to create self-assigned tasks."
        )

    if request.method != 'POST':
        return HttpResponseForbidden("POST required.")

    # ── Supervisor guard ──
    if profile.supervisor is None:
        messages.error(
            request,
            "You cannot create a self-task because you do not have a "
            "supervisor assigned. Self-allocated tasks require a supervisor "
            "for the verification workflow. Please contact your administrator."
        )
        return redirect('tracker:my_tasks')

    title = request.POST.get('title', '').strip()
    description = request.POST.get('description', '').strip()

    if not title:
        messages.error(request, "Task title is required.")
        return redirect('tracker:my_tasks')

    # Create a self-allocated checklist item — assigned_to == created_by == self
    TaskChecklist.objects.create(
        title=title,
        description=description,
        assigned_to=profile,
        created_by=profile,
        is_self_allocated=True,
        status='PENDING',
    )

    # Recalculate stats to reflect the new item
    EmployeeStats.recalculate_for(profile)

    messages.success(
        request,
        f'✅ Self-task "{title}" created. Complete it and submit for verification.'
    )
    return redirect('tracker:my_tasks')

@login_required
def meeting_details_view(request, meeting_id):
    from django.contrib import messages
    from django.http import HttpResponseForbidden
    from django.shortcuts import get_object_or_404

    meeting = get_object_or_404(Meeting, pk=meeting_id)
    profile = getattr(request.user, 'employee_profile', None)
    perms = getattr(profile, 'permissions', None) if profile else None

    # Check read access
    can_see_all_meetings = request.user.is_superuser or (perms and perms.can_manage_organization)
    if not can_see_all_meetings and profile:
        if not meeting.attendees.filter(id=profile.id).exists() and meeting.organizer != profile:
            return HttpResponseForbidden("You do not have permission to view this meeting.")

    is_erp_manager = perms and (perms.can_manage_organization or perms.can_manage_employees)
    is_organizer = profile and meeting.organizer == profile
    can_edit_minutes = is_erp_manager or is_organizer

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'update_minutes':
            if not can_edit_minutes:
                return HttpResponseForbidden("You do not have permission to edit meeting minutes.")

            meeting.minutes = request.POST.get('minutes', '')
            meeting.action_points = request.POST.get('action_points', '')
            meeting.save()
            messages.success(request, "Meeting details updated successfully.")
            return redirect('tracker:meeting_details', meeting_id=meeting.id)

        elif action == 'create_task':
            if not can_edit_minutes:
                return HttpResponseForbidden("You do not have permission to create tasks from this meeting.")

            task_title = request.POST.get('task_title', '').strip()
            task_description = request.POST.get('task_description', '').strip()
            assigned_to_id = request.POST.get('assigned_to')

            if not task_title or not assigned_to_id:
                messages.error(request, "Task title and assignee are required.")
            else:
                try:
                    assigned_to = Employee.objects.get(pk=assigned_to_id)
                    description_with_link = f"Assigned from meeting: {meeting.title}\n\n{task_description}"
                    TaskChecklist.objects.create(
                        title=task_title,
                        description=description_with_link,
                        assigned_to=assigned_to,
                        created_by=profile,
                        status='PENDING'
                    )
                    # Recalculate stats
                    EmployeeStats.recalculate_for(assigned_to)
                    messages.success(request, f"Task '{task_title}' assigned to {assigned_to.name} successfully.")
                except Employee.DoesNotExist:
                    messages.error(request, "Invalid employee selected.")
                except Exception as e:
                    messages.error(request, f"Error creating task: {e}")

            return redirect('tracker:meeting_details', meeting_id=meeting.id)

    # Mask confidential info if needed
    confidential = not (perms and perms.can_read_confidential_meetings)

    if confidential:
        meeting_agenda = 'Confidential - Access Restricted'
        meeting_minutes = 'Confidential - Access Restricted'
        meeting_action_points = 'Confidential - Access Restricted'
    else:
        meeting_agenda = meeting.agenda
        meeting_minutes = meeting.minutes
        meeting_action_points = meeting.action_points

    all_employees = Employee.objects.filter(is_active=True).order_by('name') if can_edit_minutes else []

    tasks = TaskChecklist.objects.filter(description__icontains=f"Assigned from meeting: {meeting.title}").order_by('-created_at')

    context = {
        'meeting': meeting,
        'can_edit_minutes': can_edit_minutes,
        'all_employees': all_employees,
        'meeting_agenda': meeting_agenda,
        'meeting_minutes': meeting_minutes,
        'meeting_action_points': meeting_action_points,
        'confidential': confidential,
        'tasks': tasks,
    }
    return render(request, 'meeting_details.html', context)


@login_required
def employee_analytics_view(request):
    """
    Employee Analytics: Shows who is in what role and how many tasks each person
    is currently handling.
    """
    profile = getattr(request.user, 'employee_profile', None)
    perms = getattr(profile, 'permissions', None) if profile else None

    if not perms or not perms.can_view_employee_analytics:
        return HttpResponseForbidden("You do not have permission to view employee analytics.")

    scope = perms.employee_analytics_scope

    if scope == 'own_team':
        qs = Employee.objects.filter(supervisor=profile, is_active=True)
    else:  # scope == 'all'
        qs = Employee.objects.filter(is_active=True)

    qs = qs.prefetch_related('stats').order_by('name')

    employees_data = []
    designation_stats = {}

    for emp in qs:
        # Task load = pending + awaiting
        load = 0
        completion_percentage = 0.0
        if hasattr(emp, 'stats'):
            stats = emp.stats
            load = stats.total_pending + stats.total_awaiting
            completion_percentage = float(stats.completion_percentage)

        desig = emp.designation or 'Unassigned'

        employees_data.append({
            'name': emp.name,
            'designation': desig,
            'employment_type': emp.employment_type,
            'current_load': load,
            'completion_percentage': completion_percentage,
        })

        if desig not in designation_stats:
            designation_stats[desig] = {'headcount': 0, 'total_load': 0}

        designation_stats[desig]['headcount'] += 1
        designation_stats[desig]['total_load'] += load

    role_breakdown = []
    for desig, data in designation_stats.items():
        avg_load = data['total_load'] / data['headcount'] if data['headcount'] > 0 else 0
        role_breakdown.append({
            'designation': desig,
            'headcount': data['headcount'],
            'avg_load': round(avg_load, 1)
        })

    role_breakdown.sort(key=lambda x: x['designation'])

    context = {
        'employees': employees_data,
        'role_breakdown': role_breakdown,
        'scope': scope,
    }
    return render(request, 'employee_analytics.html', context)
