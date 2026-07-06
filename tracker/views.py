import csv
import json

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
    """List all employees. select_related brings domain in one JOIN."""
    employees = (
        Employee.objects
        .select_related('domain')
        .order_by('name')
    )
    context = {
        'employees': employees,
        'generated_at': timezone.now(),
    }
    return render(request, 'employees.html', context)


@login_required
def meetings_list_view(request):
    """List all meetings. select_related for domain; prefetch_related for attendees (M2M)."""
    meetings = (
        Meeting.objects
        .select_related('domain')
        .prefetch_related('attendees')
        .order_by('-date', '-start_time')
    )
    context = {
        'meetings': meetings,
        'generated_at': timezone.now(),
    }
    return render(request, 'meetings.html', context)
