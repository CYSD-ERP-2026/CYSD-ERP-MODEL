import base64
import csv
import io
import json

import matplotlib
matplotlib.use('Agg')  # Headless mode for matplotlib
import matplotlib.pyplot as plt
import pandas as pd

from django.contrib.auth.decorators import login_required
from django.db import models
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from .models import Domain, Employee, Meeting, Project, Task


@login_required
def dashboard_view(request):
    """Main analytics dashboard."""

    # --- Summary counts ---
    total_domains = Domain.objects.filter(is_active=True).count()
    total_employees = Employee.objects.filter(is_active=True).count()
    total_meetings = Meeting.objects.count()
    completed_meetings = Meeting.objects.filter(status='completed').count()

    # --- Aggregation 1: meetings grouped by domain name ---
    by_domain_qs = (
        Meeting.objects
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
        Meeting.objects
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
        Meeting.objects
        .select_related('domain')
        .order_by('-date', '-start_time')[:10]
    )

    # Mask sensitive details for HR role
    recent_meetings = list(recent_meetings)
    profile = getattr(request.user, 'employee_profile', None)
    if profile and profile.role == 'hr':
        for m in recent_meetings:
            m.agenda = 'Confidential - Restructured Access'
            m.minutes = 'Confidential - Restructured Access'
            m.action_points = 'Confidential - Restructured Access'

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
        Meeting.objects
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
        Domain.objects
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
        Employee.objects
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
        Meeting.objects
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
            m.agenda = 'Confidential - Restructured Access'
            m.minutes = 'Confidential - Restructured Access'
            m.action_points = 'Confidential - Restructured Access'

    context = {
        'filter': meeting_filter,
        'meetings': meetings,
        'generated_at': timezone.now(),
    }
    return render(request, 'meetings.html', context)


@login_required
def policy_analytics_view(request):
    """View to analyze policy intervention scales using Pandas and Matplotlib."""
    # Query meetings (select_related for domain optimization)
    meetings_qs = Meeting.objects.select_related('domain').values(
        'intervention_scale', 'domain__name'
    )
    
    # Load into a Pandas DataFrame
    df = pd.DataFrame(list(meetings_qs))
    
    if df.empty:
        chart_image = ""
        crosstab_html = "<p class='text-muted'>No data available for analysis.</p>"
    else:
        # Fill missing values if any domain is None
        df['domain__name'] = df['domain__name'].fillna('Unassigned')
        
        # Human-readable labels for intervention scales
        scale_labels = dict(Meeting._meta.get_field('intervention_scale').choices)
        df['intervention_scale_label'] = df['intervention_scale'].map(scale_labels).fillna(df['intervention_scale'])
        
        # Generate crosstab: intervention_scale vs domain__name
        crosstab = pd.crosstab(df['intervention_scale_label'], df['domain__name'])
        
        # Render crosstab to HTML table with clean Bootstrap classes
        crosstab_html = crosstab.to_html(classes='table table-borderless table-hover table-sm align-middle mb-0')
        
        # ── Premium palette: slate blues + soft teals + muted corals ──
        PREMIUM_PALETTE = [
            '#2563eb', '#0891b2', '#0d9488', '#7c3aed',
            '#db2777', '#ea580c', '#65a30d', '#ca8a04',
        ]

        # ── Global Matplotlib style ──────────────────────────────────
        plt.rcParams.update({
            'font.family': 'DejaVu Sans',  # closest to Inter available in Matplotlib
            'font.size': 10,
            'axes.facecolor': 'none',
            'figure.facecolor': 'none',
            'text.color': '#374151',
            'axes.labelcolor': '#374151',
            'xtick.color': '#64748b',
            'ytick.color': '#64748b',
        })

        # Matplotlib visualization (stacked bar chart)
        fig, ax = plt.subplots(figsize=(8, 5))
        fig.patch.set_alpha(0)

        n_cols = len(crosstab.columns)
        bar_colours = [PREMIUM_PALETTE[i % len(PREMIUM_PALETTE)] for i in range(n_cols)]

        crosstab.plot(
            kind='bar', stacked=True, ax=ax,
            color=bar_colours, edgecolor='none', linewidth=0,
        )

        ax.set_title('Policy Intervention Scales by Domain',
                     fontsize=13, fontweight='bold', pad=14, color='#0f172a')
        ax.set_xlabel('Intervention Scale', fontsize=10, labelpad=8)
        ax.set_ylabel('Number of Meetings', fontsize=10, labelpad=8)

        plt.xticks(rotation=0, ha='center')

        # Remove harsh borders
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color('#e2e8f0')
        ax.spines['bottom'].set_color('#e2e8f0')

        # Soft y-axis only gridlines
        ax.yaxis.grid(True, linestyle='--', linewidth=0.6, alpha=0.7, color='#e2e8f0')
        ax.xaxis.grid(False)
        ax.set_axisbelow(True)

        # Refined legend
        ax.legend(
            title='Domain', title_fontsize=8,
            fontsize=8, frameon=True,
            facecolor='#ffffff', edgecolor='#e2e8f0',
            framealpha=0.9,
        )

        plt.tight_layout()

        # Save with transparent background
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight', transparent=True)
        buffer.seek(0)
        image_png = buffer.getvalue()
        buffer.close()
        plt.close(fig)
        
        # Encode to base64 string
        chart_image = base64.b64encode(image_png).decode('utf-8')
        
    context = {
        'chart_image': chart_image,
        'crosstab_html': crosstab_html,
        'generated_at': timezone.now(),
    }
    return render(request, 'analytics.html', context)


@login_required
def employee_performance_view(request):
    """View to analyze employee workloads and task efficiency using Pandas and Matplotlib."""
    profile = getattr(request.user, 'employee_profile', None)
    role = 'founder' if request.user.is_superuser else 'employee'
    if profile:
        role = profile.role

    # Enforce Row-Level Security: Filter based on role
    if role in ['founder', 'hr']:
        tasks_qs = Task.objects.select_related('assigned_to', 'project')
        employees = Employee.objects.filter(is_active=True).order_by('name')
    elif role == 'supervisor':
        allowed_ids = [profile.id] + list(profile.subordinates.values_list('id', flat=True))
        tasks_qs = Task.objects.filter(assigned_to_id__in=allowed_ids).select_related('assigned_to', 'project')
        employees = Employee.objects.filter(id__in=allowed_ids, is_active=True).order_by('name')
    else:
        allowed_ids = [profile.id] if profile else []
        tasks_qs = Task.objects.filter(assigned_to_id__in=allowed_ids).select_related('assigned_to', 'project')
        employees = Employee.objects.filter(id__in=allowed_ids, is_active=True).order_by('name')

    tasks_values = tasks_qs.values(
        'id', 'title', 'assigned_to__name', 'status', 'due_date', 'hours_logged'
    )
    df_tasks = pd.DataFrame(list(tasks_values))

    workload_chart = ""
    efficiency_chart = ""
    efficiency_percentage = 0.0

    if not df_tasks.empty:
        # Fill missing employee names
        df_tasks['assigned_to__name'] = df_tasks['assigned_to__name'].fillna('Unassigned')

        # 1. Workload Chart: Horizontal bar chart of active tasks per employee
        df_workload = df_tasks[df_tasks['status'].isin(['pending', 'in_progress'])]
        if not df_workload.empty:
            workload_series = df_workload.groupby('assigned_to__name').size().sort_values()

            # ── Premium Matplotlib style ──────────────────────────
            plt.rcParams.update({
                'font.family': 'DejaVu Sans',
                'font.size': 10,
                'axes.facecolor': 'none',
                'figure.facecolor': 'none',
                'text.color': '#374151',
                'axes.labelcolor': '#374151',
                'xtick.color': '#64748b',
                'ytick.color': '#64748b',
            })

            fig, ax = plt.subplots(figsize=(6, 4))
            fig.patch.set_alpha(0)

            workload_series.plot(kind='barh', ax=ax, color='#0891b2', edgecolor='none', linewidth=0)

            ax.set_title('Active Workload (Pending & In Progress)',
                         fontsize=11, fontweight='bold', pad=12, color='#0f172a')
            ax.set_xlabel('Number of Tasks', fontsize=9, labelpad=8)
            ax.set_ylabel('Employee', fontsize=9, labelpad=8)

            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['left'].set_color('#e2e8f0')
            ax.spines['bottom'].set_color('#e2e8f0')

            # Y-axis only soft gridlines for horizontal bars → use x-axis grid
            ax.xaxis.grid(True, linestyle='--', linewidth=0.6, alpha=0.7, color='#e2e8f0')
            ax.yaxis.grid(False)
            ax.set_axisbelow(True)

            plt.tight_layout()

            buf1 = io.BytesIO()
            plt.savefig(buf1, format='png', dpi=150, bbox_inches='tight', transparent=True)
            buf1.seek(0)
            workload_chart = base64.b64encode(buf1.getvalue()).decode('utf-8')
            buf1.close()
            plt.close(fig)

        # 2. Efficiency Chart: Pie chart of Completed vs Overdue
        completed_count = len(df_tasks[df_tasks['status'] == 'completed'])
        overdue_count = len(df_tasks[df_tasks['status'] == 'overdue'])
        
        if completed_count + overdue_count > 0:
            efficiency_percentage = (completed_count / (completed_count + overdue_count)) * 100

            plt.rcParams.update({
                'font.family': 'DejaVu Sans',
                'font.size': 10,
                'axes.facecolor': 'none',
                'figure.facecolor': 'none',
                'text.color': '#374151',
            })

            fig, ax = plt.subplots(figsize=(5, 4))
            fig.patch.set_alpha(0)

            labels = ['Completed', 'Overdue']
            sizes  = [completed_count, overdue_count]
            # Premium palette: teal-green for completed, muted coral for overdue
            colors = ['#0d9488', '#f87171']

            ax.pie(
                sizes,
                labels=labels,
                autopct='%1.1f%%',
                startangle=90,
                colors=colors,
                textprops={'fontsize': 9, 'color': '#374151'},
                wedgeprops={'edgecolor': '#ffffff', 'linewidth': 2.5},
                pctdistance=0.75,
            )
            ax.set_title('Task Completion Efficiency',
                         fontsize=11, fontweight='bold', pad=12, color='#0f172a')
            plt.tight_layout()

            buf2 = io.BytesIO()
            plt.savefig(buf2, format='png', dpi=150, bbox_inches='tight', transparent=True)
            buf2.seek(0)
            efficiency_chart = base64.b64encode(buf2.getvalue()).decode('utf-8')
            buf2.close()
            plt.close(fig)

    # Calculate employee stats for table
    employees_data = []
    for emp in employees:
        led_count = Project.objects.filter(lead_employee=emp, status='active').count()
        
        emp_tasks = Task.objects.filter(assigned_to=emp)
        active_tasks_count = emp_tasks.filter(status__in=['pending', 'in_progress']).count()
        
        # Deadlines list
        deadlines = []
        upcoming_task = emp_tasks.filter(status__in=['pending', 'in_progress', 'overdue']).order_by('due_date').first()
        upcoming_project = Project.objects.filter(lead_employee=emp, status__in=['planning', 'active']).order_by('deadline').first()
        
        if upcoming_task:
            deadlines.append((upcoming_task.due_date, f"Task: {upcoming_task.title}"))
        if upcoming_project:
            deadlines.append((upcoming_project.deadline, f"Project: {upcoming_project.title}"))
            
        if deadlines:
            deadlines.sort(key=lambda x: x[0])
            nearest_date, nearest_desc = deadlines[0]
            deadline_display = f"{nearest_date.strftime('%d %b %Y')} ({nearest_desc})"
        else:
            deadline_display = "No upcoming deadlines"
            
        employees_data.append({
            'employee': emp,
            'active_projects_led': led_count,
            'active_tasks': active_tasks_count,
            'upcoming_deadline': deadline_display,
        })

    context = {
        'workload_chart': workload_chart,
        'efficiency_chart': efficiency_chart,
        'efficiency_percentage': round(efficiency_percentage, 1),
        'employees_data': employees_data,
        'generated_at': timezone.now(),
    }
    return render(request, 'employee_analytics.html', context)
