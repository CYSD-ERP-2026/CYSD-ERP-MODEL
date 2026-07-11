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

