from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from tracker.models import Domain, Employee, Enterprise, Project, Task


class Command(BaseCommand):
    help = "Creates test enterprises, admin users, and dummy tasks for CYSD and Rasayam subdomains."

    def handle(self, *args, **options):
        self.stdout.write("Setting up test tenants...")

        # 1. Create Enterprises
        cysd_ent, created = Enterprise.objects.get_or_create(
            subdomain="cysd",
            defaults={"name": "CYSD (Centre for Youth and Social Development)"}
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Created Enterprise: CYSD"))
        else:
            self.stdout.write("Enterprise CYSD already exists.")

        rasayam_ent, created = Enterprise.objects.get_or_create(
            subdomain="rasayam",
            defaults={"name": "Rasayam Enterprises"}
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Created Enterprise: Rasayam"))
        else:
            self.stdout.write("Enterprise Rasayam already exists.")

        # 2. Setup CYSD Tenant Data
        self.stdout.write("Setting up CYSD data...")
        cysd_user, u_created = User.objects.get_or_create(
            username="cysd_admin",
            defaults={
                "email": "cysd_admin@cysd.org",
                "is_staff": True,
                "is_superuser": False,
            }
        )
        from django.contrib.auth.models import Permission
        cysd_user.is_superuser = False
        cysd_user.is_staff = True
        cysd_user.user_permissions.add(*Permission.objects.filter(content_type__app_label='tracker'))
        cysd_user.save()
        if u_created:
            cysd_user.set_password("cysdpass123")
            cysd_user.save()
            self.stdout.write(self.style.SUCCESS("Created user 'cysd_admin' (password: cysdpass123)"))

        cysd_domain, _ = Domain.objects.get_or_create(
            enterprise=cysd_ent,
            code="GEN",
            defaults={"name": "General Operations", "is_active": True}
        )

        cysd_emp, emp_created = Employee.objects.get_or_create(
            user=cysd_user,
            defaults={
                "enterprise": cysd_ent,
                "employee_id": "CYSD-ADMIN-001",
                "name": "CYSD Admin",
                "role": "founder",
                "domain": cysd_domain,
                "designation": "Executive Director",
                "email": "cysd_admin@cysd.org",
            }
        )
        if emp_created:
            self.stdout.write(self.style.SUCCESS("Created Employee profile for CYSD Admin"))

        cysd_proj, _ = Project.objects.get_or_create(
            enterprise=cysd_ent,
            title="CYSD Core Expansion Plan",
            defaults={
                "domain": cysd_domain,
                "start_date": timezone.now().date(),
                "deadline": timezone.now().date() + timezone.timedelta(days=30),
                "status": "active",
                "lead_employee": cysd_emp,
            }
        )

        cysd_task, t_created = Task.objects.get_or_create(
            enterprise=cysd_ent,
            project=cysd_proj,
            title="Draft Year-End Programmatic Report",
            defaults={
                "due_date": timezone.now().date() + timezone.timedelta(days=15),
                "status": "pending",
            }
        )
        if t_created:
            cysd_task.assigned_to.add(cysd_emp)
            self.stdout.write(self.style.SUCCESS("Created dummy task for CYSD"))

        # 3. Setup Rasayam Tenant Data
        self.stdout.write("Setting up Rasayam data...")
        rasayam_user, u_created = User.objects.get_or_create(
            username="rasayam_admin",
            defaults={
                "email": "admin@rasayam.org",
                "is_staff": True,
                "is_superuser": False,
            }
        )
        from django.contrib.auth.models import Permission
        rasayam_user.is_superuser = False
        rasayam_user.is_staff = True
        rasayam_user.user_permissions.add(*Permission.objects.filter(content_type__app_label='tracker'))
        rasayam_user.save()
        if u_created:
            rasayam_user.set_password("rasayampass123")
            rasayam_user.save()
            self.stdout.write(self.style.SUCCESS("Created user 'rasayam_admin' (password: rasayampass123)"))

        rasayam_domain, _ = Domain.objects.get_or_create(
            enterprise=rasayam_ent,
            code="OPS",
            defaults={"name": "Operations & Logistics", "is_active": True}
        )

        rasayam_emp, emp_created = Employee.objects.get_or_create(
            user=rasayam_user,
            defaults={
                "enterprise": rasayam_ent,
                "employee_id": "RAS-ADMIN-001",
                "name": "Rasayam Admin",
                "role": "founder",
                "domain": rasayam_domain,
                "designation": "Chief Operating Officer",
                "email": "admin@rasayam.org",
            }
        )
        if emp_created:
            self.stdout.write(self.style.SUCCESS("Created Employee profile for Rasayam Admin"))

        rasayam_proj, _ = Project.objects.get_or_create(
            enterprise=rasayam_ent,
            title="Rasayam ERP Implementation",
            defaults={
                "domain": rasayam_domain,
                "start_date": timezone.now().date(),
                "deadline": timezone.now().date() + timezone.timedelta(days=60),
                "status": "active",
                "lead_employee": rasayam_emp,
            }
        )

        rasayam_task, t_created = Task.objects.get_or_create(
            enterprise=rasayam_ent,
            project=rasayam_proj,
            title="Configure Subdomain Tenant Routing",
            defaults={
                "due_date": timezone.now().date() + timezone.timedelta(days=7),
                "status": "in_progress",
            }
        )
        if t_created:
            rasayam_task.assigned_to.add(rasayam_emp)
            self.stdout.write(self.style.SUCCESS("Created dummy task for Rasayam"))

        self.stdout.write(self.style.SUCCESS("Setup complete! Test tenants and mock data populated successfully."))
