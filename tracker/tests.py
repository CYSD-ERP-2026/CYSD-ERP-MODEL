import json

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from .models import (
    Domain,
    Employee,
    EmployeeStats,
    Meeting,
    TaskChecklist,
    validate_document_file,
    validate_upload_size,
)

# ═══════════════════════════════════════════════════════════════════════════
# 1. Security Validation Tests (upload guards)
# ═══════════════════════════════════════════════════════════════════════════

class SecurityValidationTests(TestCase):
    def test_large_upload_is_rejected(self):
        uploaded = SimpleUploadedFile(
            "large.pdf",
            b"x" * (6 * 1024 * 1024),
            content_type="application/pdf",
        )

        with self.assertRaises(ValidationError):
            validate_upload_size(uploaded)

    def test_disallowed_extension_is_rejected(self):
        uploaded = SimpleUploadedFile(
            "evil.exe",
            b"not a real document",
            content_type="application/octet-stream",
        )

        with self.assertRaises(ValidationError):
            validate_document_file(uploaded)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Dev Role Switcher Tests
# ═══════════════════════════════════════════════════════════════════════════

@override_settings(DEBUG=True)
class DevSwitchTests(TestCase):
    def setUp(self):
        cache.clear()
        # Create user mapped in DEV_ROLE_MAP
        self.user = User.objects.create_user(
            username="admin",
            email="admin@cysd.org",
            password="testpassword"
        )

    def test_dev_switch_creates_profile_with_tenant(self):
        response = self.client.get('/dashboard/dev-switch/founder/')

        # Verify redirect to dashboard
        self.assertEqual(response.status_code, 302)

        # Verify Employee profile was created
        employee = Employee.objects.get(user=self.user)
        self.assertIsNotNone(employee)

    def test_login_rate_limiting(self):
        cache.clear()

        # The login view is rate limited to 10 requests per 60 seconds
        for _ in range(10):
            response = self.client.get('/accounts/login/')
            self.assertEqual(response.status_code, 200)

        # 11th request should return 429
        response = self.client.get('/accounts/login/')
        self.assertEqual(response.status_code, 429)

    def test_startup_check_logs_warning_on_wildcard_hosts(self):
        from django.apps import apps
        config = apps.get_app_config('tracker')

        with self.settings(DEBUG=False, ALLOWED_HOSTS=['*']):
            with self.assertLogs('tracker.apps', level='WARNING') as cm:
                config.ready()
            self.assertTrue(any("ALLOWED_HOSTS contains '*'" in log for log in cm.output))


# ═══════════════════════════════════════════════════════════════════════════
# 3. Role-Based Permission Tests (checklist assignment & approval)
# ═══════════════════════════════════════════════════════════════════════════

class RoleBasedPermissionTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import Permission
        cache.clear()

        # Create Domain
        self.domain = Domain.objects.create(name="Domain A", code="DA")

        # Create Users & Employees
        # Supervisor
        self.super_user = User.objects.create_user(username="supervisor_u", password="password123", is_staff=True)
        self.supervisor = Employee.objects.create(
            user=self.super_user,
            name="Supervisor",
            employee_id="EMP-SUP",
            email="sup@cysd.com",
            domain=self.domain,
        )

        # Subordinate (Direct Report)
        self.sub_user = User.objects.create_user(username="sub_u", password="password123")
        self.subordinate = Employee.objects.create(
            user=self.sub_user,
            name="Subordinate",
            employee_id="EMP-SUB",
            email="sub@cysd.com",
            supervisor=self.supervisor,
            domain=self.domain,
        )

        # Non-subordinate
        self.other_user = User.objects.create_user(username="other_u", password="password123")
        self.non_subordinate = Employee.objects.create(
            user=self.other_user,
            name="Non Subordinate",
            employee_id="EMP-OTHER",
            email="other@cysd.com",
            domain=self.domain,
        )

        # Founder
        self.founder_user = User.objects.create_user(username="founder_u", password="password123")
        self.founder = Employee.objects.create(
            user=self.founder_user,
            name="Founder",
            employee_id="EMP-FND",
            email="fnd@cysd.com",
            domain=self.domain,
        )

        # HR
        self.hr_user = User.objects.create_user(username="hr_u", password="password123")
        self.hr = Employee.objects.create(
            user=self.hr_user,
            name="HR",
            employee_id="EMP-HR",
            email="hr@cysd.com",
            domain=self.domain,
        )

        # Regular Employee
        self.emp_user = User.objects.create_user(username="emp_u", password="password123")
        self.employee = Employee.objects.create(
            user=self.emp_user,
            name="Employee",
            employee_id="EMP-REG",
            email="reg@cysd.com",
            domain=self.domain,
        )

        tracker_perms = list(Permission.objects.filter(content_type__app_label='tracker'))
        self.super_user.user_permissions.add(*tracker_perms)
        self.founder_user.user_permissions.add(*tracker_perms)
        self.hr_user.user_permissions.add(*tracker_perms)

        # Set permissions manually now that role field is gone
        super_perms = self.supervisor.permissions
        super_perms.can_assign_checklist_items = True
        super_perms.can_approve_checklist_items = True
        super_perms.can_access_admin_panel = True
        super_perms.checklist_assign_scope = "own_team"
        super_perms.checklist_approve_scope = "own_team"
        super_perms.save()

        founder_perms = self.founder.permissions
        founder_perms.can_assign_checklist_items = True
        founder_perms.can_approve_checklist_items = True
        founder_perms.can_read_confidential_meetings = True
        founder_perms.can_access_admin_panel = True
        founder_perms.checklist_assign_scope = "all"
        founder_perms.checklist_approve_scope = "all"
        founder_perms.save()

        hr_perms = self.hr.permissions
        hr_perms.can_assign_checklist_items = True
        hr_perms.can_approve_checklist_items = True
        hr_perms.can_read_confidential_meetings = False
        hr_perms.can_access_admin_panel = True
        hr_perms.checklist_assign_scope = "all"
        hr_perms.checklist_approve_scope = "all"
        hr_perms.save()

    @override_settings(STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    })
    def test_supervisor_can_assign_to_direct_report(self):
        item = TaskChecklist(
            title="Direct Report Task",
            assigned_to=self.subordinate,
            created_by=self.supervisor,
        )
        item.save()
        self.assertIsNotNone(item.pk)

        # View-level test
        self.super_user.is_superuser = False
        self.super_user.is_staff = True
        self.super_user.save()
        self.client.login(username="supervisor_u", password="password123")
        response = self.client.post(
            '/admin/tracker/taskchecklist/add/',
            {
                'title': 'Admin Direct Report Task',
                'assigned_to': self.subordinate.pk,
                'created_by': self.supervisor.pk,
                'status': 'PENDING',
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(TaskChecklist.objects.filter(title='Admin Direct Report Task').exists())

    @override_settings(STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    })
    def test_supervisor_cannot_assign_to_non_subordinate(self):
        item = TaskChecklist(
            title="Non-Subordinate Task",
            assigned_to=self.non_subordinate,
            created_by=self.supervisor,
        )
        with self.assertRaises(ValidationError):
            item.save()

        # Test hitting the Django Admin creation view
        self.super_user.is_superuser = False
        self.super_user.is_staff = True
        self.super_user.save()
        self.client.login(username="supervisor_u", password="password123")

        response = self.client.post(
            '/admin/tracker/taskchecklist/add/',
            {
                'title': 'Admin Task',
                'assigned_to': self.non_subordinate.pk,
                'created_by': self.supervisor.pk,
                'status': 'PENDING',
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("does not report to them", response.content.decode('utf-8'))
        self.assertFalse(TaskChecklist.objects.filter(title='Admin Task').exists())

    @override_settings(STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    })
    def test_founder_and_hr_can_assign_to_anyone(self):
        item1 = TaskChecklist(
            title="Founder Task",
            assigned_to=self.non_subordinate,
            created_by=self.founder,
        )
        item1.save()
        self.assertIsNotNone(item1.pk)

        item2 = TaskChecklist(
            title="HR Task",
            assigned_to=self.non_subordinate,
            created_by=self.hr,
        )
        item2.save()
        self.assertIsNotNone(item2.pk)

        # View-level check for founder
        self.founder_user.is_superuser = False
        self.founder_user.is_staff = True
        self.founder_user.save()
        self.client.login(username="founder_u", password="password123")
        response = self.client.post(
            '/admin/tracker/taskchecklist/add/',
            {
                'title': 'Founder Admin Task',
                'assigned_to': self.non_subordinate.pk,
                'created_by': self.founder.pk,
                'status': 'PENDING',
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(TaskChecklist.objects.filter(title='Founder Admin Task').exists())

        # View-level check for hr
        self.hr_user.is_superuser = False
        self.hr_user.is_staff = True
        self.hr_user.save()
        self.client.login(username="hr_u", password="password123")
        response = self.client.post(
            '/admin/tracker/taskchecklist/add/',
            {
                'title': 'HR Admin Task',
                'assigned_to': self.non_subordinate.pk,
                'created_by': self.hr.pk,
                'status': 'PENDING',
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(TaskChecklist.objects.filter(title='HR Admin Task').exists())

    @override_settings(STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    })
    def test_employee_intern_volunteer_cannot_create_checklist_items(self):
        # Create Intern and Volunteer users & profiles
        intern_user = User.objects.create_user(username="intern_u", password="password123", is_staff=True)
        intern = Employee.objects.create(
            user=intern_user,
            name="Intern",
            employee_id="EMP-INT",
            email="intern@cysd.com",
            domain=self.domain,
        )

        volunteer_user = User.objects.create_user(username="volunteer_u", password="password123", is_staff=True)
        volunteer = Employee.objects.create(
            user=volunteer_user,
            name="Volunteer",
            employee_id="EMP-VOL",
            email="vol@cysd.com",
            domain=self.domain,
        )

        # Make employee user staff as well
        self.employee.permissions.can_access_admin_panel = True
        self.employee.permissions.save()
        intern.permissions.can_access_admin_panel = True
        intern.permissions.save()
        volunteer.permissions.can_access_admin_panel = True
        volunteer.permissions.save()

        # They should be blocked from the creation view (returns 403 Forbidden because they lack Django admin add permissions)
        for user, creator in [(self.emp_user, self.employee), (intern_user, intern), (volunteer_user, volunteer)]:
            self.client.login(username=user.username, password="password123")
            response = self.client.post(
                '/admin/tracker/taskchecklist/add/',
                {
                    'title': 'Unauthorized Task',
                    'assigned_to': self.non_subordinate.pk,
                    'created_by': creator.pk,
                    'status': 'PENDING',
                }
            )
            self.assertEqual(response.status_code, 403)

        # Verify they are also forbidden from the verification and resolve views
        for user in [self.emp_user, intern_user, volunteer_user]:
            self.client.login(username=user.username, password="password123")

            # Verification center view
            response = self.client.get('/dashboard/checklist/verify/')
            self.assertEqual(response.status_code, 403)

            # Resolve view
            response = self.client.post(
                '/dashboard/checklist/resolve/1/',
                {'action': 'approve'}
            )
            self.assertEqual(response.status_code, 403)

    @override_settings(STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    })
    def test_hr_masked_meeting_visibility(self):
        meeting = Meeting.objects.create(
            title="Confidential Meeting",
            date="2026-07-11",
            start_time="10:00",
            end_time="11:00",
            domain=self.domain,
            agenda="Super secret details",
            minutes="Secret minutes",
            action_points="Secret actions",
        )
        meeting.attendees.add(self.hr, self.founder)

        # Test HR user - should be masked
        self.client.login(username="hr_u", password="password123")

        # Dashboard View
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        recent_meetings = response.context['recent_meetings']
        self.assertEqual(len(recent_meetings), 1)
        self.assertEqual(recent_meetings[0].agenda, 'Confidential - Access Restricted')
        self.assertEqual(recent_meetings[0].minutes, 'Confidential - Access Restricted')
        self.assertEqual(recent_meetings[0].action_points, 'Confidential - Access Restricted')

        # Meetings List View
        response = self.client.get('/dashboard/meetings/')
        self.assertEqual(response.status_code, 200)
        meetings = response.context['meetings']
        self.assertEqual(len(meetings), 1)
        self.assertEqual(meetings[0].agenda, 'Confidential - Access Restricted')
        self.assertEqual(meetings[0].minutes, 'Confidential - Access Restricted')
        self.assertEqual(meetings[0].action_points, 'Confidential - Access Restricted')

        # Test Founder user - should NOT be masked
        self.client.login(username="founder_u", password="password123")

        # Dashboard View
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        recent_meetings = response.context['recent_meetings']
        self.assertEqual(recent_meetings[0].agenda, 'Super secret details')
        self.assertEqual(recent_meetings[0].minutes, 'Secret minutes')
        self.assertEqual(recent_meetings[0].action_points, 'Secret actions')

        # Meetings List View
        response = self.client.get('/dashboard/meetings/')
        self.assertEqual(response.status_code, 200)
        meetings = response.context['meetings']
        self.assertEqual(meetings[0].agenda, 'Super secret details')
        self.assertEqual(meetings[0].minutes, 'Secret minutes')
        self.assertEqual(meetings[0].action_points, 'Secret actions')

    @override_settings(STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    })
    def test_supervisor_cannot_resolve_non_subordinate_item_same_tenant(self):
        """RBAC scope test: A supervisor with own_team scope cannot approve
        checklist items assigned to employees outside their team, even though
        they share the same organization."""
        # Create another supervisor
        supervisor_b_user = User.objects.create_user(username="supervisor_b_u", password="password123")
        supervisor_b = Employee.objects.create(
            user=supervisor_b_user,
            name="Supervisor B",
            employee_id="EMP-SUP-B",
            email="sup_b@cysd.com",
            domain=self.domain,
        )

        # Create a checklist item for Subordinate A (direct subordinate of Supervisor A)
        checklist_item = TaskChecklist.objects.create(
            title="Subordinate A Task",
            assigned_to=self.subordinate,  # subordinate of supervisor (Supervisor A)
            created_by=self.supervisor,
            status='AWAITING_VERIFICATION',
        )

        # Log in as Supervisor B
        self.client.login(username="supervisor_b_u", password="password123")

        # Attempt to resolve the item (action: approve)
        response = self.client.post(
            f'/dashboard/checklist/resolve/{checklist_item.pk}/',
            {'action': 'approve'}
        )

        # Should return 403 Forbidden
        self.assertEqual(response.status_code, 403)

        # Confirm supervisor_b's own workload/checklist queryset is unaffected
        self.assertEqual(TaskChecklist.objects.filter(assigned_to__supervisor=supervisor_b).count(), 0)

        # Verify that the checklist item status has NOT changed to COMPLETED
        checklist_item.refresh_from_db()
        self.assertEqual(checklist_item.status, 'AWAITING_VERIFICATION')


# ═══════════════════════════════════════════════════════════════════════════
# 4. TaskChecklist Lifecycle Tests
# ═══════════════════════════════════════════════════════════════════════════

@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class TaskChecklistLifecycleTests(TestCase):
    def setUp(self):
        cache.clear()

        # Create Domain
        self.domain = Domain.objects.create(name="Domain A", code="DA")

        # Create Users & Employees
        # Supervisor
        self.super_user = User.objects.create_user(username="supervisor_u", password="password123", is_staff=True, is_superuser=False)
        self.supervisor = Employee.objects.create(
            user=self.super_user,
            name="Supervisor",
            employee_id="EMP-SUP",
            email="sup@cysd.com",
            domain=self.domain,
        )

        self.sub_user = User.objects.create_user(username="sub_u", password="password123")
        self.subordinate = Employee.objects.create(
            user=self.sub_user,
            name="Subordinate",
            employee_id="EMP-SUB",
            email="sub@cysd.com",
            supervisor=self.supervisor,
            domain=self.domain,
        )

        self.supervisor.permissions.can_assign_checklist_items = True
        self.supervisor.permissions.can_approve_checklist_items = True
        self.supervisor.permissions.checklist_assign_scope = "own_team"
        self.supervisor.permissions.checklist_approve_scope = "own_team"
        self.supervisor.permissions.save()

    def test_checklist_initial_state(self):
        item = TaskChecklist.objects.create(
            title="Initial Task",
            assigned_to=self.subordinate,
            created_by=self.supervisor,
        )
        self.assertEqual(item.status, 'PENDING')
        self.assertIsNone(item.submitted_at)
        self.assertIsNone(item.resolved_at)

    def test_checklist_submit_lifecycle(self):
        item = TaskChecklist.objects.create(
            title="Submit Task",
            assigned_to=self.subordinate,
            created_by=self.supervisor,
            status='PENDING',
        )
        # Log in as subordinate (the assigned employee)
        self.client.login(username="sub_u", password="password123")

        # Submit the item
        response = self.client.post(
            f'/dashboard/checklist/submit/{item.pk}/'
        )
        self.assertEqual(response.status_code, 302)

        # Refresh and verify
        item.refresh_from_db()
        self.assertEqual(item.status, 'AWAITING_VERIFICATION')
        self.assertIsNotNone(item.submitted_at)
        self.assertIsNone(item.resolved_at)

    def test_checklist_resolve_approve_lifecycle(self):
        item = TaskChecklist.objects.create(
            title="Resolve Task",
            assigned_to=self.subordinate,
            created_by=self.supervisor,
            status='AWAITING_VERIFICATION',
        )
        # Log in as supervisor
        self.client.login(username="supervisor_u", password="password123")

        # Resolve the item (approve)
        response = self.client.post(
            f'/dashboard/checklist/resolve/{item.pk}/',
            {'action': 'approve'}
        )
        self.assertEqual(response.status_code, 302)

        # Refresh and verify
        item.refresh_from_db()
        self.assertEqual(item.status, 'COMPLETED')
        self.assertIsNotNone(item.resolved_at)
        self.assertEqual(item.rejection_feedback, '')

    def test_checklist_resolve_reject_lifecycle(self):
        from django.utils import timezone

        item = TaskChecklist.objects.create(
            title="Reject Task",
            assigned_to=self.subordinate,
            created_by=self.supervisor,
            status='AWAITING_VERIFICATION',
            submitted_at=timezone.now(),
        )
        # Log in as supervisor
        self.client.login(username="supervisor_u", password="password123")

        # Resolve the item (reject)
        response = self.client.post(
            f'/dashboard/checklist/resolve/{item.pk}/',
            {'action': 'reject', 'feedback': 'Please redo the formatting.'}
        )
        self.assertEqual(response.status_code, 302)

        # Refresh and verify
        item.refresh_from_db()
        self.assertEqual(item.status, 'PENDING')
        self.assertIsNone(item.submitted_at)
        self.assertEqual(item.rejection_feedback, 'Please redo the formatting.')

    def test_employeestats_recalculation_signal(self):
        # 1 PENDING, 1 AWAITING_VERIFICATION
        item_pending = TaskChecklist.objects.create(
            title="Task 1",
            assigned_to=self.subordinate,
            created_by=self.supervisor,
            status='PENDING',
        )
        self.assertEqual(item_pending.status, 'PENDING')
        TaskChecklist.objects.create(
            title="Task 2",
            assigned_to=self.subordinate,
            created_by=self.supervisor,
            status='AWAITING_VERIFICATION',
        )

        # Recalculate stats initially
        stats = EmployeeStats.recalculate_for(self.subordinate)
        self.assertEqual(stats.total_assigned, 2)
        self.assertEqual(stats.total_completed, 0)
        self.assertEqual(stats.total_pending, 1)
        self.assertEqual(stats.total_awaiting, 1)
        self.assertEqual(stats.completion_percentage, 0.00)

        # Transition item_awaiting to COMPLETED programmatically to trigger post_save signal
        item_awaiting = TaskChecklist.objects.get(title="Task 2")
        item_awaiting.status = 'COMPLETED'
        item_awaiting.save()

        # Refresh stats from db
        stats.refresh_from_db()
        self.assertEqual(stats.total_assigned, 2)
        self.assertEqual(stats.total_completed, 1)
        self.assertEqual(stats.total_pending, 1)
        self.assertEqual(stats.total_awaiting, 0)
        self.assertEqual(stats.completion_percentage, 50.00)

    def test_no_unnecessary_employeestats_recalculation(self):
        from unittest.mock import patch

        item = TaskChecklist.objects.create(
            title="Test Task",
            assigned_to=self.subordinate,
            created_by=self.supervisor,
            status='PENDING',
        )

        # Let's create the stats row initially
        stats = EmployeeStats.recalculate_for(self.subordinate)
        initial_timestamp = stats.last_recalculated

        with patch('tracker.models.EmployeeStats.recalculate_for') as mock_recalc:
            # Save while status is PENDING
            item.title = "Updated Title"
            item.save()
            mock_recalc.assert_not_called()

            # Transition to AWAITING_VERIFICATION and save
            item.status = 'AWAITING_VERIFICATION'
            item.save()
            mock_recalc.assert_not_called()

            # Confirm stats last_recalculated timestamp in db hasn't changed
            stats.refresh_from_db()
            self.assertEqual(stats.last_recalculated, initial_timestamp)

            # Transition to COMPLETED and save - this should trigger recalculation
            item.status = 'COMPLETED'
            item.save()
            mock_recalc.assert_called_once_with(self.subordinate)


# ═══════════════════════════════════════════════════════════════════════════
# 5. Permission Update Tests
# ═══════════════════════════════════════════════════════════════════════════

class PermissionUpdateTests(TestCase):
    def setUp(self):
        self.hr_user = User.objects.create_user(username="hr", password="password")
        self.hr = Employee.objects.create(name="HR Manager", employee_id="HR-999", user=self.hr_user, email="hr@cyberdyne.com")
        self.hr.permissions.can_manage_employees = True
        self.hr.permissions.save()

        self.emp_user = User.objects.create_user(username="emp", password="password")
        self.emp = Employee.objects.create(name="Standard Employee", employee_id="EMP-999", user=self.emp_user, email="emp@cyberdyne.com")

    def test_hr_can_update_permissions(self):
        self.client.login(username="hr", password="password")
        payload = {
            "can_manage_organization": True,
            "checklist_assign_scope": "all"
        }
        response = self.client.patch(
            f'/dashboard/employees/{self.emp.id}/permissions/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        self.emp.permissions.refresh_from_db()
        self.assertTrue(self.emp.permissions.can_manage_organization)
        self.assertEqual(self.emp.permissions.checklist_assign_scope, "all")

    def test_employee_cannot_update_permissions(self):
        self.client.login(username="emp", password="password")
        payload = {
            "can_manage_organization": True
        }
        response = self.client.patch(
            f'/dashboard/employees/{self.emp.id}/permissions/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 403)


# ═══════════════════════════════════════════════════════════════════════════
# 6. API RBAC Tests  (replaces tenant-isolation tests)
#    Each ViewSet confirms a low-privilege account gets only their own data.
# ═══════════════════════════════════════════════════════════════════════════

class APIEmployeeViewSetTests(TestCase):
    """Verify EmployeeViewSet returns only the caller's own record for
    a low-privilege account, and all records for an account with
    can_manage_employees."""

    def setUp(self):
        cache.clear()
        self.domain = Domain.objects.create(name="D1", code="D1")

        # Low-privilege employee
        self.user_a = User.objects.create_user(username="emp_a", password="pass")
        self.emp_a = Employee.objects.create(
            user=self.user_a, name="Emp A", employee_id="A-001",
            email="a@test.com", domain=self.domain,
        )

        # Another employee
        self.user_b = User.objects.create_user(username="emp_b", password="pass")
        self.emp_b = Employee.objects.create(
            user=self.user_b, name="Emp B", employee_id="B-001",
            email="b@test.com", domain=self.domain,
        )

        # HR employee with can_manage_employees
        self.user_hr = User.objects.create_user(username="hr_api", password="pass")
        self.emp_hr = Employee.objects.create(
            user=self.user_hr, name="HR Api", employee_id="HR-API",
            email="hr_api@test.com", domain=self.domain,
        )
        self.emp_hr.permissions.can_manage_employees = True
        self.emp_hr.permissions.save()

    def test_low_privilege_sees_only_own_record(self):
        self.client.login(username="emp_a", password="pass")
        response = self.client.get('/api/v1/employees/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get('results', data)
        ids = [r['id'] for r in results]
        self.assertEqual(ids, [self.emp_a.pk])

    def test_hr_sees_all_records(self):
        self.client.login(username="hr_api", password="pass")
        response = self.client.get('/api/v1/employees/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get('results', data)
        ids = {r['id'] for r in results}
        self.assertIn(self.emp_a.pk, ids)
        self.assertIn(self.emp_b.pk, ids)
        self.assertIn(self.emp_hr.pk, ids)


class APIMeetingViewSetTests(TestCase):
    """Verify MeetingViewSet masks confidential fields for callers without
    can_read_confidential_meetings permission."""

    def setUp(self):
        cache.clear()
        self.domain = Domain.objects.create(name="D1", code="D1")

        # Employee without confidential access
        self.user = User.objects.create_user(username="basic", password="pass")
        self.emp = Employee.objects.create(
            user=self.user, name="Basic User", employee_id="BASIC-001",
            email="basic@test.com", domain=self.domain,
        )
        # Default signal sets can_read_confidential_meetings=True; override it
        self.emp.permissions.can_read_confidential_meetings = False
        self.emp.permissions.save()

        # Employee with confidential access
        self.priv_user = User.objects.create_user(username="priv", password="pass")
        self.priv_emp = Employee.objects.create(
            user=self.priv_user, name="Priv User", employee_id="PRIV-001",
            email="priv@test.com", domain=self.domain,
        )
        self.priv_emp.permissions.can_read_confidential_meetings = True
        self.priv_emp.permissions.save()

        self.meeting = Meeting.objects.create(
            title="Board Meeting", date="2026-07-11",
            agenda="Secret agenda", minutes="Secret minutes",
            action_points="Secret actions", domain=self.domain,
        )

    def test_basic_user_sees_masked_fields(self):
        self.client.login(username="basic", password="pass")
        response = self.client.get('/api/v1/meetings/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get('results', data)
        self.assertTrue(len(results) >= 1)
        m = results[0]
        self.assertEqual(m['agenda'], 'Confidential - Access Restricted')
        self.assertEqual(m['minutes'], 'Confidential - Access Restricted')
        self.assertEqual(m['action_points'], 'Confidential - Access Restricted')

    def test_privileged_user_sees_real_fields(self):
        self.client.login(username="priv", password="pass")
        response = self.client.get('/api/v1/meetings/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get('results', data)
        m = results[0]
        self.assertEqual(m['agenda'], 'Secret agenda')
        self.assertEqual(m['minutes'], 'Secret minutes')
        self.assertEqual(m['action_points'], 'Secret actions')


class APITaskViewSetTests(TestCase):
    """Verify TaskViewSet scopes results by caller's permissions."""

    def setUp(self):
        from .models import Project
        cache.clear()
        self.domain = Domain.objects.create(name="D1", code="D1")

        # Supervisor with own_team scope
        self.sup_user = User.objects.create_user(username="sup", password="pass")
        self.supervisor = Employee.objects.create(
            user=self.sup_user, name="Supervisor", employee_id="SUP-API",
            email="sup_api@test.com", domain=self.domain,
        )
        self.supervisor.permissions.can_approve_checklist_items = True
        self.supervisor.permissions.checklist_approve_scope = "own_team"
        self.supervisor.permissions.save()

        # Subordinate of supervisor
        self.sub_user = User.objects.create_user(username="sub", password="pass")
        self.subordinate = Employee.objects.create(
            user=self.sub_user, name="Subordinate", employee_id="SUB-API",
            email="sub_api@test.com", domain=self.domain,
            supervisor=self.supervisor,
        )

        # Unrelated employee
        self.other_user = User.objects.create_user(username="other", password="pass")
        self.other_emp = Employee.objects.create(
            user=self.other_user, name="Other", employee_id="OTH-API",
            email="other_api@test.com", domain=self.domain,
        )

        # Create a project and tasks
        from django.utils import timezone
        self.project = Project.objects.create(
            title="Test Project", domain=self.domain,
            deadline=timezone.now().date(),
        )
        from .models import Task
        self.task_sub = Task.objects.create(
            title="Sub Task", project=self.project,
            due_date=timezone.now().date(),
        )
        self.task_sub.assigned_to.add(self.subordinate)

        self.task_other = Task.objects.create(
            title="Other Task", project=self.project,
            due_date=timezone.now().date(),
        )
        self.task_other.assigned_to.add(self.other_emp)

    def test_low_privilege_sees_only_own_tasks(self):
        """Base-role employee sees only tasks assigned to them."""
        self.client.login(username="other", password="pass")
        response = self.client.get('/api/v1/tasks/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get('results', data)
        ids = {r['id'] for r in results}
        self.assertIn(self.task_other.pk, ids)
        self.assertNotIn(self.task_sub.pk, ids)

    def test_supervisor_sees_team_tasks(self):
        """Supervisor with own_team scope sees tasks of direct reports."""
        self.client.login(username="sup", password="pass")
        response = self.client.get('/api/v1/tasks/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get('results', data)
        ids = {r['id'] for r in results}
        self.assertIn(self.task_sub.pk, ids)
        self.assertNotIn(self.task_other.pk, ids)


class APITaskChecklistViewSetTests(TestCase):
    """Verify TaskChecklistViewSet scopes results by caller's permissions.

    Replaces the old tenant-isolation test: instead of checking that
    'Enterprise A can't see Enterprise B's items', we verify that an
    employee-role account can't see another team's checklist items."""

    def setUp(self):
        cache.clear()
        self.domain = Domain.objects.create(name="D1", code="D1")

        # Supervisor with own_team scope
        self.sup_user = User.objects.create_user(username="sup", password="pass")
        self.supervisor = Employee.objects.create(
            user=self.sup_user, name="Supervisor", employee_id="SUP-CK",
            email="sup_ck@test.com", domain=self.domain,
        )
        self.supervisor.permissions.can_approve_checklist_items = True
        self.supervisor.permissions.can_assign_checklist_items = True
        self.supervisor.permissions.checklist_approve_scope = "own_team"
        self.supervisor.permissions.checklist_assign_scope = "own_team"
        self.supervisor.permissions.save()

        # Subordinate
        self.sub_user = User.objects.create_user(username="sub", password="pass")
        self.subordinate = Employee.objects.create(
            user=self.sub_user, name="Subordinate", employee_id="SUB-CK",
            email="sub_ck@test.com", domain=self.domain,
            supervisor=self.supervisor,
        )

        # Another team's employee (no supervisor relationship)
        self.other_user = User.objects.create_user(username="other", password="pass")
        self.other_emp = Employee.objects.create(
            user=self.other_user, name="Other Employee", employee_id="OTH-CK",
            email="other_ck@test.com", domain=self.domain,
        )

        # Founder with 'all' scope
        self.founder_user = User.objects.create_user(username="founder_ck", password="pass")
        self.founder_emp = Employee.objects.create(
            user=self.founder_user, name="Founder CK", employee_id="FND-CK",
            email="fnd_ck@test.com", domain=self.domain,
        )
        self.founder_emp.permissions.can_approve_checklist_items = True
        self.founder_emp.permissions.can_assign_checklist_items = True
        self.founder_emp.permissions.checklist_approve_scope = "all"
        self.founder_emp.permissions.checklist_assign_scope = "all"
        self.founder_emp.permissions.save()

        # Create checklist items
        self.item_sub = TaskChecklist.objects.create(
            title="Sub Checklist", assigned_to=self.subordinate,
            created_by=self.supervisor, status='PENDING',
        )
        self.item_other = TaskChecklist.objects.create(
            title="Other Checklist", assigned_to=self.other_emp,
            created_by=self.founder_emp, status='PENDING',
        )

    def test_low_privilege_sees_only_own_checklist_items(self):
        """Employee-role account can't see another team's checklist items.
        This replaces the old tenant-isolation assertion."""
        self.client.login(username="other", password="pass")
        response = self.client.get('/api/v1/checklists/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get('results', data)
        ids = {r['id'] for r in results}
        # Should see own item only
        self.assertIn(self.item_other.pk, ids)
        self.assertNotIn(self.item_sub.pk, ids)

    def test_supervisor_sees_team_checklist_items(self):
        """Supervisor with own_team scope sees only direct reports' items."""
        self.client.login(username="sup", password="pass")
        response = self.client.get('/api/v1/checklists/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get('results', data)
        ids = {r['id'] for r in results}
        self.assertIn(self.item_sub.pk, ids)
        self.assertNotIn(self.item_other.pk, ids)

    def test_founder_sees_all_checklist_items(self):
        """Founder with 'all' scope sees everything."""
        self.client.login(username="founder_ck", password="pass")
        response = self.client.get('/api/v1/checklists/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get('results', data)
        ids = {r['id'] for r in results}
        self.assertIn(self.item_sub.pk, ids)
        self.assertIn(self.item_other.pk, ids)
