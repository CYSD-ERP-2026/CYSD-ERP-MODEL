from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

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

        from tracker.models import Enterprise
        # Get or create an Enterprise
        self.enterprise, _ = Enterprise.objects.get_or_create(
            subdomain="cysd",
            defaults={"name": "CYSD"}
        )
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
        response = client.get('/dashboard/dev-switch/founder/', HTTP_HOST='cysd.localhost')

        # Verify redirect to dashboard
        self.assertEqual(response.status_code, 302)

        # Verify Employee profile was created with the correct tenant
        employee = Employee.objects.get(user=self.user)
        self.assertEqual(employee.enterprise, self.enterprise)
        self.assertEqual(employee.role, 'founder')

    def test_login_rate_limiting(self):
        from django.core.cache import cache
        cache.clear()

        # The login view is rate limited to 5 requests per 60 seconds
        for _ in range(5):
            response = self.client.get('/accounts/login/', HTTP_HOST='cysd.localhost')
            self.assertEqual(response.status_code, 200)

        # 6th request should return 429
        response = self.client.get('/accounts/login/', HTTP_HOST='cysd.localhost')
        self.assertEqual(response.status_code, 429)

    def test_startup_check_logs_warning_on_wildcard_hosts(self):
        from django.apps import apps
        config = apps.get_app_config('tracker')

        with self.settings(DEBUG=False, ALLOWED_HOSTS=['*']):
            with self.assertLogs('tracker.apps', level='WARNING') as cm:
                config.ready()
            self.assertTrue(any("ALLOWED_HOSTS contains '*'" in log for log in cm.output))


class MultiTenantDataIsolationTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        from django.core.cache import cache

        from tracker.models import Domain, Employee, Enterprise, Meeting, TaskChecklist
        cache.clear()

        # 1. Create two Enterprises
        self.tenant_a = Enterprise.objects.create(name="Tenant A", subdomain="a")
        self.tenant_b = Enterprise.objects.create(name="Tenant B", subdomain="b")

        # 2. Create Domains for both
        self.domain_a = Domain.objects.create(name="Domain A", code="DA", enterprise=self.tenant_a)
        self.domain_b = Domain.objects.create(name="Domain B", code="DB", enterprise=self.tenant_b)

        # 3. Create Employees
        self.user_a = User.objects.create_user(username="user_a", password="password123")
        self.employee_a = Employee.objects.create(
            user=self.user_a,
            name="Employee A",
            employee_id="EMP-A",
            email="a@tenant.com",
            designation="Manager",
            role="founder",
            enterprise=self.tenant_a,
            domain=self.domain_a,
        )

        self.user_b = User.objects.create_user(username="user_b", password="password123")
        self.employee_b = Employee.objects.create(
            user=self.user_b,
            name="Employee B",
            employee_id="EMP-B",
            email="b@tenant.com",
            designation="Manager",
            role="founder",
            enterprise=self.tenant_b,
            domain=self.domain_b,
        )

        # 4. Create Meetings
        self.meeting_a = Meeting.objects.create(
            title="Meeting A",
            date="2026-07-11",
            start_time="10:00",
            end_time="11:00",
            enterprise=self.tenant_a,
            domain=self.domain_a,
            agenda="Secret Agenda A",
        )
        self.meeting_a.attendees.add(self.employee_a)

        self.meeting_b = Meeting.objects.create(
            title="Meeting B",
            date="2026-07-11",
            start_time="10:00",
            end_time="11:00",
            enterprise=self.tenant_b,
            domain=self.domain_b,
            agenda="Secret Agenda B",
        )
        self.meeting_b.attendees.add(self.employee_b)

        # 5. Create a Checklist Item for Tenant B
        self.checklist_b = TaskChecklist.objects.create(
            title="Checklist B",
            enterprise=self.tenant_b,
            assigned_to=self.employee_b,
            created_by=self.employee_b,
            status='AWAITING_VERIFICATION',
        )

    @override_settings(STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    })
    def test_list_views_isolate_tenant_data(self):
        # Log in user A
        self.client.login(username="user_a", password="password123")

        views_to_test = [
            ('/dashboard/', 'tracker:dashboard'),
            ('/dashboard/employees/', 'tracker:employees'),
            ('/dashboard/meetings/', 'tracker:meetings'),
            ('/dashboard/domains/', 'tracker:domains'),
        ]

        for url, route_name in views_to_test:
            # Request on Tenant A's subdomain
            response = self.client.get(url, HTTP_HOST='a.localhost')
            self.assertEqual(response.status_code, 200)

            # Check context/HTML does not contain Tenant B's data
            content_str = response.content.decode('utf-8')
            self.assertNotIn("Tenant B", content_str)
            self.assertNotIn("Domain B", content_str)
            self.assertNotIn("Employee B", content_str)
            self.assertNotIn("Meeting B", content_str)

    def test_direct_access_to_other_tenant_record_is_blocked(self):
        self.client.login(username="user_a", password="password123")

        # Attempt to resolve Tenant B's checklist item using Tenant A's subdomain
        response = self.client.post(
            f'/dashboard/checklist/resolve/{self.checklist_b.pk}/',
            {'action': 'approve'},
            HTTP_HOST='a.localhost'
        )
        # It should either be a 404 or 403 (Forbidden)
        self.assertIn(response.status_code, [403, 404])

        # Attempt to submit Tenant B's checklist item
        response = self.client.post(
            f'/dashboard/checklist/submit/{self.checklist_b.pk}/',
            HTTP_HOST='a.localhost'
        )
        # Should redirect back or return 403/404, status should not change
        self.checklist_b.refresh_from_db()
        self.assertEqual(self.checklist_b.status, 'AWAITING_VERIFICATION')

    def test_middleware_unknown_subdomain(self):
        # Request on an unknown subdomain
        response = self.client.get('/dashboard/', HTTP_HOST='unknown.localhost')
        self.assertEqual(response.status_code, 404)

    def test_middleware_exempt_paths(self):
        # Path /admin/ should not raise 404 even without a tenant
        response = self.client.get('/admin/', HTTP_HOST='localhost')
        self.assertNotEqual(response.status_code, 404)

    def test_middleware_cross_tenant_mismatch_logout(self):
        # Authenticated user A attempts to access Tenant B's workspace
        self.client.login(username="user_a", password="password123")

        response = self.client.get('/dashboard/', HTTP_HOST='b.localhost', follow=True)

        # User should be logged out and redirected to login page with a permission/error message
        self.assertRedirects(response, '/accounts/login/')

        # Verify the user is logged out (cannot access authenticated views anymore)
        response_dash = self.client.get('/dashboard/', HTTP_HOST='a.localhost')
        self.assertRedirects(response_dash, '/accounts/login/?next=/dashboard/')

        # Check messages in response for the error message
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)
        self.assertIn("You do not have permission to access the workspace for 'Tenant B'.", str(messages[0]))


class RoleBasedPermissionTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        from django.core.cache import cache

        from tracker.models import Domain, Employee, Enterprise
        cache.clear()

        # Create Enterprise
        self.tenant = Enterprise.objects.create(name="Enterprise A", subdomain="cysd-role")

        # Create Domain
        self.domain = Domain.objects.create(name="Domain A", code="DA", enterprise=self.tenant)

        # Create Users & Employees
        # Supervisor
        self.super_user = User.objects.create_user(username="supervisor_u", password="password123", is_staff=True)
        self.supervisor = Employee.objects.create(
            user=self.super_user,
            name="Supervisor",
            employee_id="EMP-SUP",
            email="sup@cysd.com",
            role="supervisor",
            enterprise=self.tenant,
            domain=self.domain,
        )

        # Subordinate (Direct Report)
        self.sub_user = User.objects.create_user(username="sub_u", password="password123")
        self.subordinate = Employee.objects.create(
            user=self.sub_user,
            name="Subordinate",
            employee_id="EMP-SUB",
            email="sub@cysd.com",
            role="employee",
            supervisor=self.supervisor,
            enterprise=self.tenant,
            domain=self.domain,
        )

        # Non-subordinate
        self.other_user = User.objects.create_user(username="other_u", password="password123")
        self.non_subordinate = Employee.objects.create(
            user=self.other_user,
            name="Non Subordinate",
            employee_id="EMP-OTHER",
            email="other@cysd.com",
            role="employee",
            enterprise=self.tenant,
            domain=self.domain,
        )

        # Founder
        self.founder_user = User.objects.create_user(username="founder_u", password="password123")
        self.founder = Employee.objects.create(
            user=self.founder_user,
            name="Founder",
            employee_id="EMP-FND",
            email="fnd@cysd.com",
            role="founder",
            enterprise=self.tenant,
            domain=self.domain,
        )

        # HR
        self.hr_user = User.objects.create_user(username="hr_u", password="password123")
        self.hr = Employee.objects.create(
            user=self.hr_user,
            name="HR",
            employee_id="EMP-HR",
            email="hr@cysd.com",
            role="hr",
            enterprise=self.tenant,
            domain=self.domain,
        )

        # Regular Employee
        self.emp_user = User.objects.create_user(username="emp_u", password="password123")
        self.employee = Employee.objects.create(
            user=self.emp_user,
            name="Employee",
            employee_id="EMP-REG",
            email="reg@cysd.com",
            role="employee",
            enterprise=self.tenant,
            domain=self.domain,
        )

    def test_supervisor_can_assign_to_direct_report(self):
        from tracker.models import TaskChecklist
        item = TaskChecklist(
            title="Direct Report Task",
            enterprise=self.tenant,
            assigned_to=self.subordinate,
            created_by=self.supervisor,
        )
        item.save()
        self.assertIsNotNone(item.pk)

    def test_supervisor_cannot_assign_to_non_subordinate(self):
        from django.core.exceptions import ValidationError

        from tracker.models import TaskChecklist

        item = TaskChecklist(
            title="Non-Subordinate Task",
            enterprise=self.tenant,
            assigned_to=self.non_subordinate,
            created_by=self.supervisor,
        )
        with self.assertRaises(ValidationError):
            item.save()

        # Test hitting the Django Admin creation view
        self.super_user.is_superuser = True
        self.super_user.save()
        self.client.login(username="supervisor_u", password="password123")

        response = self.client.post(
            '/admin/tracker/taskchecklist/add/',
            {
                'title': 'Admin Task',
                'assigned_to': self.non_subordinate.pk,
                'created_by': self.supervisor.pk,
                'status': 'PENDING',
            },
            HTTP_HOST='cysd-role.localhost'
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("does not report to them", response.content.decode('utf-8'))

    def test_founder_and_hr_can_assign_to_anyone(self):
        from tracker.models import TaskChecklist

        item1 = TaskChecklist(
            title="Founder Task",
            enterprise=self.tenant,
            assigned_to=self.non_subordinate,
            created_by=self.founder,
        )
        item1.save()
        self.assertIsNotNone(item1.pk)

        item2 = TaskChecklist(
            title="HR Task",
            enterprise=self.tenant,
            assigned_to=self.non_subordinate,
            created_by=self.hr,
        )
        item2.save()
        self.assertIsNotNone(item2.pk)

    def test_employee_intern_volunteer_cannot_access_verification_center(self):
        self.client.login(username="emp_u", password="password123")
        response = self.client.get('/dashboard/checklist/verify/', HTTP_HOST='cysd-role.localhost')
        self.assertEqual(response.status_code, 403)

    @override_settings(STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    })
    def test_hr_masked_meeting_visibility_on_dashboard(self):
        from tracker.models import Meeting
        Meeting.objects.create(
            title="Confidential Meeting",
            date="2026-07-11",
            start_time="10:00",
            end_time="11:00",
            enterprise=self.tenant,
            domain=self.domain,
            agenda="Super secret details",
            minutes="Secret minutes",
            action_points="Secret actions",
        )
        self.client.login(username="hr_u", password="password123")

        response = self.client.get('/dashboard/', HTTP_HOST='cysd-role.localhost')
        self.assertEqual(response.status_code, 200)

        recent_meetings = response.context['recent_meetings']
        self.assertEqual(len(recent_meetings), 1)
        self.assertEqual(recent_meetings[0].agenda, 'Confidential - Access Restricted')
        self.assertEqual(recent_meetings[0].minutes, 'Confidential - Access Restricted')
        self.assertEqual(recent_meetings[0].action_points, 'Confidential - Access Restricted')

