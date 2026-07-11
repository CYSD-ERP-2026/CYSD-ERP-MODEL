import os

import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cysd_erp.settings')
django.setup()

import datetime
from decimal import Decimal

from django.contrib.auth.models import User

from tracker.models import Domain, Employee, Meeting, Project, Task


def reseed():
    print("Starting clean hierarchy re-seeding...")

    # 1. Clear existing database objects (except admin user and its profile)
    Task.objects.all().delete()
    Project.objects.all().delete()
    Meeting.objects.all().delete()
    Domain.objects.all().delete()

    # Delete all employees except the one linked to 'admin'
    admin_user = User.objects.get(username='admin')
    admin_profile = Employee.objects.filter(user=admin_user).first()
    if admin_profile:
        Employee.objects.exclude(id=admin_profile.id).delete()
    else:
        # Create it if it doesn't exist
        Employee.objects.all().delete()
        admin_profile = Employee.objects.create(
            user=admin_user,
            employee_id="CYSD-FOUNDER-001",
            name="Admin Founder",
            email="admin@cysd.org",
            role="founder",
            is_active=True,
            designation="Founder & Executive Director"
        )

    # Delete all users except 'admin'
    User.objects.exclude(username='admin').delete()

    # Create the requested domains
    domain_srl = Domain.objects.create(name="Sustainable Rural Livelihoods", code="SRL", lead="Admin Founder")
    domain_ied = Domain.objects.create(name="Inclusive Education", code="IED", lead="Sujata Patnaik")
    domain_wem = Domain.objects.create(name="Women Empowerment & SHGs", code="WEM", lead="Harish Rao")
    domain_hln = Domain.objects.create(name="Health & Nutrition", code="HLN", lead="Siddharth Mohanty")

    print("Database cleared. Creating new hierarchy...")

    # 2. Create users and linked employees
    # Passwords for all users is set to 'admin123' for ease of testing
    def create_user_and_employee(username, name, role, supervisor, designation, email, domain):
        user = User.objects.create_user(
            username=username,
            password='admin123',
            email=email
        )
        # Set is_staff status for higher roles
        if role in ['founder', 'hr', 'supervisor']:
            user.is_staff = True
        user.save()

        emp = Employee.objects.create(
            user=user,
            employee_id=f"CYSD-{role.upper()}-{username.upper()}"[:30],
            name=name,
            email=email,
            role=role,
            supervisor=supervisor,
            designation=designation,
            domain=domain,
            is_active=True
        )
        return emp

    # Link founder admin_profile to domain_srl
    admin_profile.domain = domain_srl
    admin_profile.save()

    # Create HR Manager (reports to founder)
    hr_emp = create_user_and_employee(
        username='hr_user',
        name='Harish Rao',
        role='hr',
        supervisor=admin_profile,
        designation='Human Resources Manager',
        email='hr@cysd.org',
        domain=domain_wem
    )

    # Create Supervisor 1 (reports to founder)
    sup1_emp = create_user_and_employee(
        username='supervisor',
        name='Siddharth Mohanty',
        role='supervisor',
        supervisor=admin_profile,
        designation='Senior Program Manager (Livelihoods)',
        email='sid@cysd.org',
        domain=domain_srl
    )

    # Create Supervisor 2 (reports to founder)
    sup2_emp = create_user_and_employee(
        username='supervisor_b',
        name='Sujata Patnaik',
        role='supervisor',
        supervisor=admin_profile,
        designation='Senior Coordinator (Education)',
        email='sujata@cysd.org',
        domain=domain_ied
    )

    # Create Employees under Supervisor 1
    emp1_emp = create_user_and_employee(
        username='employee',
        name='Elina Das',
        role='employee',
        supervisor=sup1_emp,
        designation='Field Officer',
        email='elina@cysd.org',
        domain=domain_srl
    )

    emp2_emp = create_user_and_employee(
        username='emp_b',
        name='Bikram Keshari',
        role='employee',
        supervisor=sup1_emp,
        designation='Data Analyst',
        email='bikram@cysd.org',
        domain=domain_wem
    )

    # Create Intern under Supervisor 1
    intern_emp = create_user_and_employee(
        username='intern_a',
        name='Ipsita Priyadarshini',
        role='intern',
        supervisor=sup1_emp,
        designation='Field Research Intern',
        email='ipsita@cysd.org',
        domain=domain_srl
    )

    # Create Volunteer under Supervisor 2
    volunteer_emp = create_user_and_employee(
        username='volunteer_a',
        name='Vikram Seth',
        role='volunteer',
        supervisor=sup2_emp,
        designation='Community Volunteer',
        email='vikram@cysd.org',
        domain=domain_ied
    )

    print("Hierarchy created. Seeding projects, tasks, and meetings...")

    # 3. Create Projects
    proj1 = Project.objects.create(
        title="Village Micro-enterprise Scale-up",
        domain=domain_srl,
        start_date=datetime.date.today() - datetime.timedelta(days=60),
        deadline=datetime.date.today() + datetime.timedelta(days=90),
        status="active",
        lead_employee=sup1_emp
    )

    proj2 = Project.objects.create(
        title="Tribal Education Capacity Support",
        domain=domain_ied,
        start_date=datetime.date.today() - datetime.timedelta(days=30),
        deadline=datetime.date.today() + datetime.timedelta(days=120),
        status="active",
        lead_employee=sup2_emp
    )

    # 4. Create Tasks
    def create_task(title, project, assigned_list, due_date, status, hours_logged):
        t = Task.objects.create(
            title=title,
            project=project,
            due_date=due_date,
            status=status,
            hours_logged=hours_logged
        )
        t.assigned_to.set(assigned_list)
        return t

    # Under Siddharth's team (Supervisor 1):
    # Elina's tasks
    create_task(
        title="Map village enterprise clusters",
        project=proj1,
        assigned_list=[emp1_emp],
        due_date=datetime.date.today() + datetime.timedelta(days=15),
        status="in_progress",
        hours_logged=Decimal("12.50")
    )
    create_task(
        title="Conduct baseline surveys in Bargarh",
        project=proj1,
        assigned_list=[emp1_emp],
        due_date=datetime.date.today() - datetime.timedelta(days=5),
        status="overdue",
        hours_logged=Decimal("4.00")
    )
    create_task(
        title="Prepare SHG loan linkage forms",
        project=proj1,
        assigned_list=[emp1_emp],
        due_date=datetime.date.today() - datetime.timedelta(days=10),
        status="completed",
        hours_logged=Decimal("18.00")
    )

    # Bikram's tasks
    create_task(
        title="Design data validation script",
        project=proj1,
        assigned_list=[emp2_emp],
        due_date=datetime.date.today() + datetime.timedelta(days=30),
        status="pending",
        hours_logged=Decimal("0.00")
    )
    create_task(
        title="Clean and consolidate baseline datasets",
        project=proj1,
        assigned_list=[emp2_emp],
        due_date=datetime.date.today() - datetime.timedelta(days=2),
        status="completed",
        hours_logged=Decimal("25.00")
    )

    # Ipsita's (Intern) tasks
    create_task(
        title="Draft qualitative case study reports",
        project=proj1,
        assigned_list=[intern_emp],
        due_date=datetime.date.today() + datetime.timedelta(days=10),
        status="in_progress",
        hours_logged=Decimal("8.00")
    )

    # Let's also create a Shared Task assigned to BOTH Elina and Bikram to test ManyToMany!
    create_task(
        title="Joint fieldwork: Enterprise baseline reporting",
        project=proj1,
        assigned_list=[emp1_emp, emp2_emp],
        due_date=datetime.date.today() + datetime.timedelta(days=20),
        status="in_progress",
        hours_logged=Decimal("15.00")
    )

    # Under Sujata's team (Supervisor 2):
    # Vikram's (Volunteer) tasks
    create_task(
        title="Distribute learning kits in tribal blocks",
        project=proj2,
        assigned_list=[volunteer_emp],
        due_date=datetime.date.today() + datetime.timedelta(days=5),
        status="in_progress",
        hours_logged=Decimal("6.00")
    )
    create_task(
        title="Verify local school attendance logs",
        project=proj2,
        assigned_list=[volunteer_emp],
        due_date=datetime.date.today() - datetime.timedelta(days=4),
        status="completed",
        hours_logged=Decimal("10.00")
    )

    # 5. Create Meetings
    # --- Under Siddharth Mohanty (Supervisor 1) ---
    m1 = Meeting.objects.create(
        title="SRL Quarterly Progress Review",
        domain=domain_srl,
        meeting_type="internal",
        status="completed",
        intervention_scale="district",
        date=datetime.date.today() - datetime.timedelta(days=15),
        start_time=datetime.time(10, 0),
        end_time=datetime.time(11, 30),
        venue="CYSD Head Office, Bhubaneswar",
        agenda="1. Align project goals\n2. Distribute target villages\n3. Set reporting structure",
        minutes="Meeting successfully aligned the target goals. Siddharth gave the opening remarks and Elina noted details.",
        action_points="- Siddharth to share maps by Friday\n- Elina to start surveys",
        organised_by=sup1_emp.name
    )
    m1.attendees.set([sup1_emp, emp1_emp, emp2_emp, intern_emp])

    m2 = Meeting.objects.create(
        title="Nutrition Integration Consultative Meet",
        domain=domain_hln,
        meeting_type="partner",
        status="completed",
        intervention_scale="state",
        date=datetime.date.today() - datetime.timedelta(days=8),
        start_time=datetime.time(11, 0),
        end_time=datetime.time(13, 0),
        venue="Hotel Swosti, Bhubaneswar",
        agenda="1. Address maternal nutrition issues\n2. Coordinate with health workers",
        minutes="Aligned NHM indicators with regional intervention guidelines.",
        action_points="- Harish to update recruitment for community nutrition helpers.",
        organised_by=sup1_emp.name
    )
    m2.attendees.set([sup1_emp, hr_emp, emp1_emp])

    m3 = Meeting.objects.create(
        title="SHG Enterprise Convergence Planning",
        domain=domain_wem,
        meeting_type="internal",
        status="scheduled",
        intervention_scale="district",
        date=datetime.date.today() + datetime.timedelta(days=5),
        start_time=datetime.time(15, 0),
        end_time=datetime.time(16, 30),
        venue="Google Meet (Online)",
        agenda="1. Assess microcredit linkage forms\n2. Discuss handloom cluster support",
        organised_by=sup1_emp.name
    )
    m3.attendees.set([sup1_emp, emp2_emp])

    # --- Under Sujata Patnaik (Supervisor 2) ---
    m4 = Meeting.objects.create(
        title="Inclusive Tribal Education Review",
        domain=domain_ied,
        meeting_type="internal",
        status="scheduled",
        intervention_scale="community",
        date=datetime.date.today() + datetime.timedelta(days=3),
        start_time=datetime.time(14, 0),
        end_time=datetime.time(15, 30),
        venue="Zoom Video Call",
        agenda="1. Review learning kit distribution status\n2. Discuss volunteer coordination",
        organised_by=sup2_emp.name
    )
    m4.attendees.set([sup2_emp, volunteer_emp])

    m5 = Meeting.objects.create(
        title="Livelihood Education Bridge Course Planning",
        domain=domain_srl,
        meeting_type="internal",
        status="completed",
        intervention_scale="community",
        date=datetime.date.today() - datetime.timedelta(days=12),
        start_time=datetime.time(10, 0),
        end_time=datetime.time(12, 0),
        venue="Block Development Office, Phulbani",
        agenda="1. Design curriculum for school dropouts\n2. Discuss farm skill classes",
        minutes="Agreed on standard 60-day bridge syllabus template.",
        action_points="- Elina to supply local dialect vocab guides.",
        organised_by=sup2_emp.name
    )
    m5.attendees.set([sup2_emp, emp1_emp])

    m6 = Meeting.objects.create(
        title="WASH in Schools Infrastructure Audit",
        domain=domain_hln,
        meeting_type="field",
        status="scheduled",
        intervention_scale="district",
        date=datetime.date.today() + datetime.timedelta(days=10),
        start_time=datetime.time(10, 30),
        end_time=datetime.time(13, 0),
        venue="District Collectorate Conference Hall, Koraput",
        agenda="1. Evaluate toilet construction progress\n2. Align safe drinking water assets",
        organised_by=sup2_emp.name
    )
    m6.attendees.set([sup2_emp, volunteer_emp, hr_emp])

    print("Reseeding complete! All roles successfully mapped.")

if __name__ == "__main__":
    reseed()
