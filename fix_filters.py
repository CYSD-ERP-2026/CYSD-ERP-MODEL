import re

with open('tracker/filters.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the imports
content = content.replace(
    '    Employee,\\n    Meeting,\\n)',
    '    Employee,\\n    Meeting,\\n    Project,\\n)'
)

# Update EmployeeFilter definition
employee_filter_start = content.find('class EmployeeFilter')
if employee_filter_start != -1:
    old_employee_filter = content[employee_filter_start:]
    
    # We will manually rebuild EmployeeFilter
    new_employee_filter = '''class EmployeeFilter(django_filters.FilterSet):
    """
    Filters for the Employees list view.
    """
    name = django_filters.CharFilter(
        field_name='name',
        lookup_expr='icontains',
        label='Name contains',
        widget=TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Search name…'}),
    )
    domains = django_filters.ModelMultipleChoiceFilter(
        queryset=Domain.objects.filter(is_active=True).order_by('name'),
        label='Domains',
    )
    projects = django_filters.ModelMultipleChoiceFilter(
        queryset=Project.objects.all(),
        label='Projects'
    )
    designation = django_filters.CharFilter(
        field_name='designation',
        lookup_expr='icontains',
        label='Designation contains',
        widget=TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Search designation…'}),
    )

    class Meta:
        model = Employee
        fields = ['name', 'domains', 'projects', 'designation']

    def __init__(self, *args, **kwargs):
        request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if request and hasattr(request, 'tenant'):
            qs = Domain.objects.filter(is_active=True).order_by('name')
            if 'domains' in self.form.fields:
                self.form.fields['domains'].queryset = qs
'''
    
    content = content[:employee_filter_start] + new_employee_filter

with open('tracker/filters.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed filters.py')
