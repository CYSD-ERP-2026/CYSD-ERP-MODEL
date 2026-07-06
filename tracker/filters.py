"""
tracker/filters.py
==================
django-filter FilterSet classes for Meetings and Employees list views.
All widgets are bootstrapped with form-select / form-control classes so
they integrate seamlessly with the existing Bootstrap 5 templates.
"""
import django_filters
from django.forms import Select, TextInput

from .models import Domain, Employee, Meeting, INTERVENTION_SCALE_CHOICES, MEETING_STATUS_CHOICES

# Reusable widget kwargs
_TEXT_WIDGET = TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': ''})
_SELECT_WIDGET = Select(attrs={'class': 'form-select form-select-sm'})


class MeetingFilter(django_filters.FilterSet):
    """
    Filters for the Meetings list view.

    Fields:
        title              – case-insensitive substring search
        domain             – exact FK lookup
        intervention_scale – exact choice lookup
        status             – exact choice lookup
    """
    title = django_filters.CharFilter(
        field_name='title',
        lookup_expr='icontains',
        label='Title contains',
        widget=TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Search title…'}),
    )
    domain = django_filters.ModelChoiceFilter(
        queryset=Domain.objects.filter(is_active=True).order_by('name'),
        label='Domain',
        empty_label='All Domains',
        widget=Select(attrs={'class': 'form-select form-select-sm'}),
    )
    intervention_scale = django_filters.ChoiceFilter(
        choices=INTERVENTION_SCALE_CHOICES,
        label='Intervention Scale',
        empty_label='All Scales',
        widget=Select(attrs={'class': 'form-select form-select-sm'}),
    )
    status = django_filters.ChoiceFilter(
        choices=MEETING_STATUS_CHOICES,
        label='Status',
        empty_label='All Statuses',
        widget=Select(attrs={'class': 'form-select form-select-sm'}),
    )

    class Meta:
        model = Meeting
        fields = ['title', 'domain', 'intervention_scale', 'status']


class EmployeeFilter(django_filters.FilterSet):
    """
    Filters for the Employees list view.

    Fields:
        name        – case-insensitive substring search
        domain      – exact FK lookup
        designation – case-insensitive substring search
    """
    name = django_filters.CharFilter(
        field_name='name',
        lookup_expr='icontains',
        label='Name contains',
        widget=TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Search name…'}),
    )
    domain = django_filters.ModelChoiceFilter(
        queryset=Domain.objects.filter(is_active=True).order_by('name'),
        label='Domain',
        empty_label='All Domains',
        widget=Select(attrs={'class': 'form-select form-select-sm'}),
    )
    designation = django_filters.CharFilter(
        field_name='designation',
        lookup_expr='icontains',
        label='Designation contains',
        widget=TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Search designation…'}),
    )

    class Meta:
        model = Employee
        fields = ['name', 'domain', 'designation']
