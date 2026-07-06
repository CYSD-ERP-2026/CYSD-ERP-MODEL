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
    context = {
        'filter': meeting_filter,
        'meetings': meeting_filter.qs,
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
        crosstab_html = crosstab.to_html(classes='table table-bordered table-striped table-hover table-sm mb-0')
        
        # Matplotlib visualization (stacked bar chart)
        fig, ax = plt.subplots(figsize=(8, 5))
        
        # Plot stacked bar chart with viridis palette
        crosstab.plot(kind='bar', stacked=True, ax=ax, colormap='viridis', edgecolor='none')
        
        ax.set_title('Policy Intervention Scales by Domain', fontsize=14, fontweight='bold', pad=15, color='#0d2b55')
        ax.set_xlabel('Intervention Scale', fontsize=11, fontweight='semibold', labelpad=10)
        ax.set_ylabel('Number of Meetings', fontsize=11, fontweight='semibold', labelpad=10)
        
        # Style layout and labels
        plt.xticks(rotation=0)  # keep labels horizontal
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color('#cbd5e1')
        ax.spines['bottom'].set_color('#cbd5e1')
        ax.yaxis.grid(True, linestyle='--', alpha=0.5, color='#cbd5e1')
        ax.set_axisbelow(True)
        
        # Add legend
        ax.legend(title='Domain', frameon=True, facecolor='#f8fafc', edgecolor='#cbd5e1')
        
        plt.tight_layout()
        
        # Save plot to BytesIO buffer
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
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
    # Query all tasks
    tasks_qs = Task.objects.select_related('assigned_to', 'project').values(
        'id', 'title', 'assigned_to__name', 'status', 'due_date', 'hours_logged'
    )
    df_tasks = pd.DataFrame(list(tasks_qs))

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
            
            fig, ax = plt.subplots(figsize=(6, 4))
            workload_series.plot(kind='barh', ax=ax, color='#0a7e8c', edgecolor='none')
            ax.set_title('Active Workload (Pending & In Progress Tasks)', fontsize=12, fontweight='bold', pad=12, color='#0d2b55')
            ax.set_xlabel('Number of Tasks', fontsize=10, fontweight='semibold')
            ax.set_ylabel('Employee', fontsize=10, fontweight='semibold')
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['left'].set_color('#cbd5e1')
            ax.spines['bottom'].set_color('#cbd5e1')
            ax.xaxis.grid(True, linestyle='--', alpha=0.5, color='#cbd5e1')
            ax.set_axisbelow(True)
            plt.tight_layout()
            
            # Save to buffer
            buf1 = io.BytesIO()
            plt.savefig(buf1, format='png', dpi=150, bbox_inches='tight')
            buf1.seek(0)
            workload_chart = base64.b64encode(buf1.getvalue()).decode('utf-8')
            buf1.close()
            plt.close(fig)

        # 2. Efficiency Chart: Pie chart of Completed vs Overdue
        completed_count = len(df_tasks[df_tasks['status'] == 'completed'])
        overdue_count = len(df_tasks[df_tasks['status'] == 'overdue'])
        
        if completed_count + overdue_count > 0:
            efficiency_percentage = (completed_count / (completed_count + overdue_count)) * 100
            
            fig, ax = plt.subplots(figsize=(5, 4))
            labels = ['Completed', 'Overdue']
            sizes = [completed_count, overdue_count]
            colors = ['#16a34a', '#dc2626'] # Green vs Red
            
            ax.pie(
                sizes, 
                labels=labels, 
                autopct='%1.1f%%', 
                startangle=90, 
                colors=colors, 
                textprops={'fontsize': 10, 'weight': 'semibold'},
                wedgeprops={'edgecolor': '#fff', 'linewidth': 2}
            )
            ax.set_title('Task Completion Efficiency', fontsize=12, fontweight='bold', pad=12, color='#0d2b55')
            plt.tight_layout()
            
            # Save to buffer
            buf2 = io.BytesIO()
            plt.savefig(buf2, format='png', dpi=150, bbox_inches='tight')
            buf2.seek(0)
            efficiency_chart = base64.b64encode(buf2.getvalue()).decode('utf-8')
            buf2.close()
            plt.close(fig)

    # Calculate employee stats for table
    employees_data = []
    employees = Employee.objects.filter(is_active=True).order_by('name')
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
