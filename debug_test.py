import os
import sys
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cysd_erp.settings")
django.setup()

from django.test.utils import setup_test_environment
setup_test_environment()

from django.test.client import Client
from django.contrib.auth.models import User
from tracker.models import Employee, TaskChecklist, Enterprise, Domain

tenant, _ = Enterprise.objects.get_or_create(name="Test Org", subdomain="testorg")
domain, _ = Domain.objects.get_or_create(name="IT", enterprise=tenant)

sup_u, _ = User.objects.get_or_create(username="sup", defaults={"is_staff": True})
supervisor, _ = Employee.objects.get_or_create(
    user=sup_u, defaults=dict(name="Sup", employee_id="E1", email="e1@example.com", role="supervisor", enterprise=tenant, domain=domain)
)

non_sub_u, _ = User.objects.get_or_create(username="non_sub")
non_subordinate, _ = Employee.objects.get_or_create(
    user=non_sub_u, defaults=dict(name="Non Sub", employee_id="E2", email="e2@example.com", role="employee", enterprise=tenant, domain=domain)
)

tc = TaskChecklist(
    title='Admin Task',
    assigned_to=non_subordinate,
    created_by=supervisor,
    status='PENDING',
    enterprise=tenant
)
tc.clean()
