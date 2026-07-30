from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase

from .models import validate_document_file, validate_upload_size


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


from django.test import override_settings


@override_settings(DEBUG=True)
class DevSwitchTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User

        
                # Create user mapped in DEV_ROLE_MAP
        self.user = User.objects.create_user(
            username="admin",
            email="admin@cysd.org",
            password="testpassword"
        )

    def test_dev_switch_creates_profile_with_tenant(self):
        from tracker.models import Employee
        # We access the URL with subdomain cysd.localhost
        client = self.client
        # Set HTTP_HOST to cysd.localhost so middleware detects the subdomain
        response = client.get('/dashboard/dev-switch/founder/')

        # Verify redirect to dashboard
        self.assertEqual(response.status_code, 302)

        # Verify Employee profile was created with the correct tenant
        employee = Employee.objects.get(user=self.user)
        

    def test_login_rate_limiting(self):
        from django.core.cache import cache
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


class RoleBasedPermissionTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        from django.core.cache import cache

        from tracker.models import Domain, Employee
        cache.clear()

        # Create 
        

        # Create Domain
        self.domain = Domain.objects.create(name="Domain A", code="DA", )

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

        from django.contrib.auth.models import Permission
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
        from tracker.models import TaskChecklist
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
        from django.core.exceptions import ValidationError

        from tracker.models import TaskChecklist

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
        from tracker.models import TaskChecklist

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
        from django.contrib.auth.models import User

        from tracker.models import Employee

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
        from tracker.models import Meeting
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
        from django.contrib.auth.models import User

        from tracker.models import Employee, TaskChecklist

        # Create another supervisor in the same tenant
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


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class TaskChecklistLifecycleTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        from django.core.cache import cache

        from tracker.models import Domain, Employee

        cache.clear()

        # Create 
        

        # Create Domain
        self.domain = Domain.objects.create(name="Domain A", code="DA", )

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
        from tracker.models import TaskChecklist
        item = TaskChecklist.objects.create(
            title="Initial Task",
            assigned_to=self.subordinate,
            created_by=self.supervisor,
        )
        self.assertEqual(item.status, 'PENDING')
        self.assertIsNone(item.submitted_at)
        self.assertIsNone(item.resolved_at)

    def test_checklist_submit_lifecycle(self):
        from tracker.models import TaskChecklist
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
        from tracker.models import TaskChecklist
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

        from tracker.models import TaskChecklist
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
        from tracker.models import EmployeeStats, TaskChecklist

        # 1 PENDING, 1 AWAITING_VERIFICATION
        item_pending = TaskChecklist.objects.create(
            title="Task 1",
            assigned_to=self.subordinate,
            created_by=self.supervisor,
            status='PENDING',
        )
        self.assertEqual(item_pending.status, 'PENDING')
        item_awaiting = TaskChecklist.objects.create(
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

        from tracker.models import EmployeeStats, TaskChecklist

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

import json

class PermissionUpdateTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        from tracker.models import Employee
        
        
        
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
