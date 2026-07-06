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

from .models import Domain, Employee, Meeting


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
