from django.urls import path
from . import views

app_name = 'tracker'

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('domains/', views.domains_list_view, name='domains'),
    path('employees/', views.employees_list_view, name='employees'),
    path('meetings/', views.meetings_list_view, name='meetings'),
    path('analytics/', views.policy_analytics_view, name='analytics'),
    path('employee-analytics/', views.employee_performance_view, name='employee_analytics'),
    path('my-tasks/', views.my_tasks_view, name='my_tasks'),
    path('export/', views.export_meetings_csv, name='export_meetings_csv'),
    path('setup-organization/', views.setup_organization_view, name='setup_organization'),

    # ── Task Checklist ────────────────────────────────────────────────────
    path('checklist/', views.my_tasks_view, name='checklist_employee'),
    path('checklist/submit/<int:item_id>/', views.checklist_submit_view, name='checklist_submit'),
    path('checklist/verify/', views.checklist_supervisor_view, name='checklist_supervisor'),
    path('checklist/resolve/<int:item_id>/', views.checklist_resolve_view, name='checklist_resolve'),

    # Dev-only masquerade endpoint – blocked in production by the view itself
    path('dev-switch/<str:role_name>/', views.dev_role_switch_view, name='dev_switch'),
]
