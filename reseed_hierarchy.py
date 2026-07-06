import os
import sys
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cysd_erp.settings')
django.setup()

from django.contrib.auth.models import User
from tracker.models import Domain, Employee, Project, Task, Meeting
from django.utils import timezone
import datetime
from decimal import Decimal

def reseed():
    print("Starting clean hierarchy re-seeding...")
    
    # 1. Clear existing database objects (except admin user and its profile)
    Task.objects.all().delete()
    Project.objects.all().delete()
    Meeting.objects.all().delete()
    
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
    
    # Ensure we have at least one domain
    domain = Domain.objects.first()
    if not domain:
        domain = Domain.objects.create(
            name="Sustainable Rural Livelihoods",
            code="SRL",
            lead="Admin Founder"
        )
        
    print("Database cleared. Creating new hierarchy...")
    
    # 2. Create users and linked employees
    # Passwords for all users is set to 'admin123' for ease of testing
    def create_user_and_employee(username, name, role, supervisor, designation, email):
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

    # Create HR Manager (reports to founder)
    hr_emp = create_user_and_employee(
        username='hr_user',
        name='Harish Rao',
        role='hr',
        supervisor=admin_profile,
        designation='Human Resources Manager',
        email='hr@cysd.org'
    )
    
    # Create Supervisor 1 (reports to founder)
    sup1_emp = create_user_and_employee(
        username='supervisor',
        name='Siddharth Mohanty',
        role='supervisor',
        supervisor=admin_profile,
        designation='Senior Program Manager (Livelihoods)',
        email='sid@cysd.org'
    )

    # Create Supervisor 2 (reports to founder)
    sup2_emp = create_user_and_employee(
        username='supervisor_b',
        name='Sujata Patnaik',
        role='supervisor',
        supervisor=admin_profile,
        designation='Senior Coordinator (Education)',
        email='sujata@cysd.org'
    )
    
    # Create Employees under Supervisor 1
    emp1_emp = create_user_and_employee(
        username='employee',
        name='Elina Das',
        role='employee',
        supervisor=sup1_emp,
        designation='Field Officer',
        email='elina@cysd.org'
    )

    emp2_emp = create_user_and_employee(
        username='emp_b',
        name='Bikram Keshari',
        role='employee',
        supervisor=sup1_emp,
        designation='Data Analyst',
        email='bikram@cysd.org'
    )
    
    # Create Intern under Supervisor 1
    intern_emp = create_user_and_employee(
        username='intern_a',
        name='Ipsita Priyadarshini',
        role='intern',
        supervisor=sup1_emp,
        designation='Field Research Intern',
        email='ipsita@cysd.org'
    )
    
    # Create Volunteer under Supervisor 2
    volunteer_emp = create_user_and_employee(
        username='volunteer_a',
        name='Vikram Seth',
        role='volunteer',
        supervisor=sup2_emp,
        designation='Community Volunteer',
        email='vikram@cysd.org'
    )

    print("Hierarchy created. Seeding projects, tasks, and meetings...")
    
    # 3. Create Projects
    proj1 = Project.objects.create(
        title="Village Micro-enterprise Scale-up",
        domain=domain,
        start_date=datetime.date.today() - datetime.timedelta(days=60),
        deadline=datetime.date.today() + datetime.timedelta(days=90),
        status="active",
        lead_employee=sup1_emp
    )

    proj2 = Project.objects.create(
        title="Tribal Education Capacity Support",
        domain=domain,
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
    m1 = Meeting.objects.create(
        title="Livelihoods Project Kick-off",
        domain=domain,
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
        title="Monthly Tribal Education Review",
        domain=domain,
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
    m2.attendees.set([sup2_emp, volunteer_emp])

    print("Reseeding complete! All roles successfully mapped.")

if __name__ == "__main__":
    reseed()
