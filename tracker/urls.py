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
    path('export/', views.export_meetings_csv, name='export_meetings_csv'),
]
