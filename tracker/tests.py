from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase

from .models import validate_document_file, validate_upload_size
import copy
import django.template.context
_original_copy = copy.copy
import django.template.context
def _patched_context_copy(self):
    duplicate = object.__new__(type(self))
    duplicate.__dict__.update(self.__dict__)
    if hasattr(self, 'dicts'):
        duplicate.dicts = [d.copy() if hasattr(d, 'copy') else d for d in self.dicts]
    return duplicate
django.template.context.BaseContext.__copy__ = _patched_context_copy


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

    @override_settings(STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    })
    def test_admin_list_views_fallback_to_owner_tenant_on_bare_domain(self):
        from django.contrib.auth.models import Permission, User

        from tracker.models import (
            Domain,
            Employee,
            Meeting,
            Project,
            Task,
            TaskChecklist,
        )

        founder_user = User.objects.create_user(
            username='founder_admin_a',
            password='password123',
            is_staff=True,
        )
        founder_user.user_permissions.add(*Permission.objects.filter(content_type__app_label='tracker'))
        founder_user.save()
        Employee.objects.create(
            user=founder_user,
            name='Founder Admin A',
            employee_id='EMP-A-ADMIN',
            email='founder-admin-a@tenant.com',
            designation='Founder',
            role='founder',
            enterprise=self.tenant_a,
            domain=self.domain_a,
        )

        # Create complete set of objects for Tenant A
        project_a = Project.objects.create(
            title='Project A Title',
            enterprise=self.tenant_a,
            domain=self.domain_a,
            lead_employee=self.employee_a,
            status='active',
            start_date='2026-07-11',
            deadline='2026-07-20',
        )
        task_a = Task.objects.create(
            title='Task A Title',
            enterprise=self.tenant_a,
            project=project_a,
            due_date='2026-07-20',
            status='pending',
        )
        task_a.assigned_to.add(self.employee_a)
        checklist_a = TaskChecklist.objects.create(
            title='Checklist A Title',
            enterprise=self.tenant_a,
            assigned_to=self.employee_a,
            created_by=self.employee_a,
            status='PENDING',
        )
        self.assertEqual(checklist_a.enterprise, self.tenant_a)

        # Create complete set of objects for Tenant B
        project_b = Project.objects.create(
            title='Project B Title',
            enterprise=self.tenant_b,
            domain=self.domain_b,
            lead_employee=self.employee_b,
            status='active',
            start_date='2026-07-11',
            deadline='2026-07-20',
        )
        task_b = Task.objects.create(
            title='Task B Title',
            enterprise=self.tenant_b,
            project=project_b,
            due_date='2026-07-20',
            status='pending',
        )
        task_b.assigned_to.add(self.employee_b)
        checklist_b = TaskChecklist.objects.create(
            title='Checklist B Title',
            enterprise=self.tenant_b,
            assigned_to=self.employee_b,
            created_by=self.employee_b,
            status='PENDING',
        )
        self.assertEqual(checklist_b.enterprise, self.tenant_b)

        request_factory = RequestFactory()
        admin_models = [
            (Domain, '/admin/tracker/domain/'),
            (Employee, '/admin/tracker/employee/'),
            (Meeting, '/admin/tracker/meeting/'),
            (Project, '/admin/tracker/project/'),
            (Task, '/admin/tracker/task/'),
            (TaskChecklist, '/admin/tracker/taskchecklist/'),
        ]

        self.client.login(username='founder_admin_a', password='password123')

        for model_class, admin_url in admin_models:
            # 1. Test using request factory & get_queryset directly
            request = request_factory.get(admin_url, HTTP_HOST='localhost')
            request.user = founder_user
            request.tenant = None

            admin_instance = admin.site._registry[model_class]
            queryset = admin_instance.get_queryset(request)

            self.assertTrue(queryset.filter(enterprise=self.tenant_a).exists())
            self.assertFalse(queryset.filter(enterprise=self.tenant_b).exists())

            # 2. Test actual GET request using test client
            response = self.client.get(admin_url, HTTP_HOST='localhost')
            self.assertEqual(response.status_code, 200)
            html_content = response.content.decode('utf-8')

            # Assert Tenant A records (from self.tenant_a) are visible, and Tenant B are not
            if model_class == Domain:
                self.assertIn("Domain A", html_content)
                self.assertNotIn("Domain B", html_content)
            elif model_class == Employee:
                self.assertIn("Employee A", html_content)
                self.assertNotIn("Employee B", html_content)
            elif model_class == Meeting:
                self.assertIn("Meeting A", html_content)
                self.assertNotIn("Meeting B", html_content)
            elif model_class == Project:
                self.assertIn("Project A Title", html_content)
                self.assertNotIn("Project B Title", html_content)
            elif model_class == Task:
                self.assertIn("Task A Title", html_content)
                self.assertNotIn("Task B Title", html_content)
            elif model_class == TaskChecklist:
                self.assertIn("Checklist A Title", html_content)
                self.assertNotIn("Checklist B Title", html_content)

    @override_settings(STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    })
    def test_admin_list_view_for_user_without_employee_profile_is_empty(self):
        from django.contrib.auth.models import Permission, User

        from tracker.models import (
            Domain,
            Employee,
            Meeting,
            Project,
            Task,
            TaskChecklist,
        )

        user_without_profile = User.objects.create_user(
            username='staff_no_profile',
            password='password123',
            is_staff=True,
        )
        user_without_profile.user_permissions.add(*Permission.objects.filter(content_type__app_label='tracker'))
        user_without_profile.save()

        self.client.login(username='staff_no_profile', password='password123')

        admin_models = [
            (Domain, '/admin/tracker/domain/'),
            (Employee, '/admin/tracker/employee/'),
            (Meeting, '/admin/tracker/meeting/'),
            (Project, '/admin/tracker/project/'),
            (Task, '/admin/tracker/task/'),
            (TaskChecklist, '/admin/tracker/taskchecklist/'),
        ]

        for model_class, admin_url in admin_models:
            # 1. Request Factory Queryset verification
            request = RequestFactory().get(admin_url, HTTP_HOST='localhost')
            request.user = user_without_profile
            request.tenant = None

            admin_instance = admin.site._registry[model_class]
            queryset = admin_instance.get_queryset(request)
            self.assertEqual(queryset.count(), 0)

            # 2. Client GET request verification
            response = self.client.get(admin_url, HTTP_HOST='localhost')
            self.assertEqual(response.status_code, 200)
            html_content = response.content.decode('utf-8')
            if model_class == Domain:
                self.assertNotIn("Domain A", html_content)
                self.assertNotIn("Domain B", html_content)
            elif model_class == Employee:
                self.assertNotIn("Employee A", html_content)
                self.assertNotIn("Employee B", html_content)
            elif model_class == Meeting:
                self.assertNotIn("Meeting A", html_content)
                self.assertNotIn("Meeting B", html_content)
            elif model_class == Project:
                self.assertNotIn("Project A Title", html_content)
                self.assertNotIn("Project B Title", html_content)
            elif model_class == Task:
                self.assertNotIn("Task A Title", html_content)
                self.assertNotIn("Task B Title", html_content)
            elif model_class == TaskChecklist:
                self.assertNotIn("Checklist A Title", html_content)
                self.assertNotIn("Checklist B Title", html_content)

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

    def test_nonexistent_subdomain_shows_branded_error_page(self):
        # 1. With DEBUG = True
        with self.settings(DEBUG=True):
            response = self.client.get('/dashboard/', HTTP_HOST='nonexistent.localhost')
            self.assertEqual(response.status_code, 404)
            self.assertIn("Workspace Not Found", response.content.decode('utf-8'))
            self.assertIn("Developer Note", response.content.decode('utf-8'))
            self.assertIn("a", response.content.decode('utf-8'))
            self.assertIn("b", response.content.decode('utf-8'))

        # 2. With DEBUG = False
        with self.settings(DEBUG=False):
            response = self.client.get('/dashboard/', HTTP_HOST='nonexistent.localhost')
            self.assertEqual(response.status_code, 404)
            self.assertIn("Workspace Not Found", response.content.decode('utf-8'))
            self.assertNotIn("Developer Note", response.content.decode('utf-8'))

    def test_no_workspace_specified_shows_branded_error_page(self):
        # 1. With DEBUG = True
        with self.settings(DEBUG=True):
            response = self.client.get('/dashboard/', HTTP_HOST='localhost')
            self.assertEqual(response.status_code, 404)
            self.assertIn("No Workspace Specified", response.content.decode('utf-8'))
            self.assertIn("Developer Note", response.content.decode('utf-8'))

        # 2. With DEBUG = False
        with self.settings(DEBUG=False):
            response = self.client.get('/dashboard/', HTTP_HOST='localhost')
            self.assertEqual(response.status_code, 404)
            self.assertIn("No Workspace Specified", response.content.decode('utf-8'))
            self.assertNotIn("Developer Note", response.content.decode('utf-8'))


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

        from django.contrib.auth.models import Permission
        tracker_perms = list(Permission.objects.filter(content_type__app_label='tracker'))
        self.super_user.user_permissions.add(*tracker_perms)
        self.founder_user.user_permissions.add(*tracker_perms)
        self.hr_user.user_permissions.add(*tracker_perms)

    @override_settings(STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    })
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
            },
            HTTP_HOST='cysd-role.localhost'
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
            enterprise=self.tenant,
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
            },
            HTTP_HOST='cysd-role.localhost'
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
            },
            HTTP_HOST='cysd-role.localhost'
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
            },
            HTTP_HOST='cysd-role.localhost'
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
            role="intern",
            enterprise=self.tenant,
            domain=self.domain,
        )

        volunteer_user = User.objects.create_user(username="volunteer_u", password="password123", is_staff=True)
        volunteer = Employee.objects.create(
            user=volunteer_user,
            name="Volunteer",
            employee_id="EMP-VOL",
            email="vol@cysd.com",
            role="volunteer",
            enterprise=self.tenant,
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
                },
                HTTP_HOST='cysd-role.localhost'
            )
            self.assertEqual(response.status_code, 403)

        # Verify they are also forbidden from the verification and resolve views
        for user in [self.emp_user, intern_user, volunteer_user]:
            self.client.login(username=user.username, password="password123")

            # Verification center view
            response = self.client.get('/dashboard/checklist/verify/', HTTP_HOST='cysd-role.localhost')
            self.assertEqual(response.status_code, 403)

            # Resolve view
            response = self.client.post(
                '/dashboard/checklist/resolve/1/',
                {'action': 'approve'},
                HTTP_HOST='cysd-role.localhost'
            )
            self.assertEqual(response.status_code, 403)

    @override_settings(STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    })
    def test_hr_masked_meeting_visibility(self):
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

        # Test HR user - should be masked
        self.client.login(username="hr_u", password="password123")

        # Dashboard View
        response = self.client.get('/dashboard/', HTTP_HOST='cysd-role.localhost')
        self.assertEqual(response.status_code, 200)
        recent_meetings = response.context['recent_meetings']
        self.assertEqual(len(recent_meetings), 1)
        self.assertEqual(recent_meetings[0].agenda, 'Confidential - Access Restricted')
        self.assertEqual(recent_meetings[0].minutes, 'Confidential - Access Restricted')
        self.assertEqual(recent_meetings[0].action_points, 'Confidential - Access Restricted')

        # Meetings List View
        response = self.client.get('/dashboard/meetings/', HTTP_HOST='cysd-role.localhost')
        self.assertEqual(response.status_code, 200)
        meetings = response.context['meetings']
        self.assertEqual(len(meetings), 1)
        self.assertEqual(meetings[0].agenda, 'Confidential - Access Restricted')
        self.assertEqual(meetings[0].minutes, 'Confidential - Access Restricted')
        self.assertEqual(meetings[0].action_points, 'Confidential - Access Restricted')

        # Test Founder user - should NOT be masked
        self.client.login(username="founder_u", password="password123")

        # Dashboard View
        response = self.client.get('/dashboard/', HTTP_HOST='cysd-role.localhost')
        self.assertEqual(response.status_code, 200)
        recent_meetings = response.context['recent_meetings']
        self.assertEqual(recent_meetings[0].agenda, 'Super secret details')
        self.assertEqual(recent_meetings[0].minutes, 'Secret minutes')
        self.assertEqual(recent_meetings[0].action_points, 'Secret actions')

        # Meetings List View
        response = self.client.get('/dashboard/meetings/', HTTP_HOST='cysd-role.localhost')
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
            role="supervisor",
            enterprise=self.tenant,
            domain=self.domain,
        )

        # Create a checklist item for Subordinate A (direct subordinate of Supervisor A)
        checklist_item = TaskChecklist.objects.create(
            title="Subordinate A Task",
            enterprise=self.tenant,
            assigned_to=self.subordinate,  # subordinate of supervisor (Supervisor A)
            created_by=self.supervisor,
            status='AWAITING_VERIFICATION',
        )

        # Log in as Supervisor B
        self.client.login(username="supervisor_b_u", password="password123")

        # Attempt to resolve the item (action: approve)
        response = self.client.post(
            f'/dashboard/checklist/resolve/{checklist_item.pk}/',
            {'action': 'approve'},
            HTTP_HOST='cysd-role.localhost'
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

        from tracker.models import Domain, Employee, Enterprise

        cache.clear()

        # Create Enterprise
        self.tenant = Enterprise.objects.create(name="Enterprise A", subdomain="cysd-role")

        # Create Domain
        self.domain = Domain.objects.create(name="Domain A", code="DA", enterprise=self.tenant)

        # Create Users & Employees
        # Supervisor
        self.super_user = User.objects.create_user(username="supervisor_u", password="password123", is_staff=True, is_superuser=False)
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

    def test_checklist_initial_state(self):
        from tracker.models import TaskChecklist
        item = TaskChecklist.objects.create(
            title="Initial Task",
            enterprise=self.tenant,
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
            enterprise=self.tenant,
            assigned_to=self.subordinate,
            created_by=self.supervisor,
            status='PENDING',
        )
        # Log in as subordinate (the assigned employee)
        self.client.login(username="sub_u", password="password123")

        # Submit the item
        response = self.client.post(
            f'/dashboard/checklist/submit/{item.pk}/',
            HTTP_HOST='cysd-role.localhost'
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
            enterprise=self.tenant,
            assigned_to=self.subordinate,
            created_by=self.supervisor,
            status='AWAITING_VERIFICATION',
        )
        # Log in as supervisor
        self.client.login(username="supervisor_u", password="password123")

        # Resolve the item (approve)
        response = self.client.post(
            f'/dashboard/checklist/resolve/{item.pk}/',
            {'action': 'approve'},
            HTTP_HOST='cysd-role.localhost'
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
            enterprise=self.tenant,
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
            {'action': 'reject', 'feedback': 'Please redo the formatting.'},
            HTTP_HOST='cysd-role.localhost'
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
            enterprise=self.tenant,
            assigned_to=self.subordinate,
            created_by=self.supervisor,
            status='PENDING',
        )
        self.assertEqual(item_pending.status, 'PENDING')
        item_awaiting = TaskChecklist.objects.create(
            title="Task 2",
            enterprise=self.tenant,
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
            enterprise=self.tenant,
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
        from tracker.models import Enterprise, Employee
        
        self.tenant = Enterprise.objects.create(name="Cyberdyne", subdomain="cyber")
        
        self.hr_user = User.objects.create_user(username="hr", password="password")
        self.hr = Employee.objects.create(name="HR Manager", employee_id="HR-999", user=self.hr_user, enterprise=self.tenant, role="hr", email="hr@cyberdyne.com")
        self.hr.permissions.can_manage_employees = True
        self.hr.permissions.save()
        
        self.emp_user = User.objects.create_user(username="emp", password="password")
        self.emp = Employee.objects.create(name="Standard Employee", employee_id="EMP-999", user=self.emp_user, enterprise=self.tenant, role="employee", email="emp@cyberdyne.com")

    def test_hr_can_update_permissions(self):
        self.client.login(username="hr", password="password")
        payload = {
            "can_manage_organization": True,
            "checklist_assign_scope": "all"
        }
        response = self.client.patch(
            f'/dashboard/employees/{self.emp.id}/permissions/',
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_HOST='cyber.localhost'
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
            content_type='application/json',
            HTTP_HOST='cyber.localhost'
        )
        self.assertEqual(response.status_code, 403)
