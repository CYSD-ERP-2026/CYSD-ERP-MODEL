from django.urls import path

from . import views

app_name = 'tracker'

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('domains/', views.domains_list_view, name='domains'),
    path('employees/', views.employees_list_view, name='employees'),
    path('employees/export/', views.export_employees_csv, name='export_employees_csv'),
    path('employees/import/', views.import_employees_csv, name='import_employees_csv'),
    path('employees/<int:emp_id>/permissions/', views.update_employee_permissions, name='update_permissions'),
    path('meetings/', views.meetings_list_view, name='meetings'),
    path('meetings/create/', views.meeting_create_view, name='meeting_create'),
    path('meetings/<int:meeting_id>/', views.meeting_details_view, name='meeting_details'),
    path('my-tasks/', views.my_tasks_view, name='my_tasks'),
    path('export/', views.export_meetings_csv, name='export_meetings_csv'),
    path('analytics/', views.employee_analytics_view, name='employee_analytics'),


    # ── Task Checklist ────────────────────────────────────────────────────
    path('checklist/', views.my_tasks_view, name='checklist_employee'),
    path('checklist/submit/<int:item_id>/', views.checklist_submit_view, name='checklist_submit'),
    path('checklist/verify/', views.checklist_supervisor_view, name='checklist_supervisor'),
    path('checklist/create/', views.checklist_create_view, name='checklist_create'),
    path('checklist/resolve/<int:item_id>/', views.checklist_resolve_view, name='checklist_resolve'),
    path('self-task/create/', views.create_self_task, name='create_self_task'),

    # Dev-only masquerade endpoint – blocked in production by the view itself
    path('dev-switch/<str:role_name>/', views.dev_role_switch_view, name='dev_switch'),
]
