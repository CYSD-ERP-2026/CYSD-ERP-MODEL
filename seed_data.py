"""
seed_data.py
============
Standalone Django seed script for CYSD ERP.
Run via:  python manage.py shell < seed_data.py

Creates (idempotent – skips each section if data already exists):
  • 6  Domains
  • 20 Employees
  • 10 Projects
  • 35 Meetings  (with M2M attendees)
  • 90 Tasks
"""

import os
import sys
import random
import datetime
from decimal import Decimal

# ── Bootstrap Django ─────────────────────────────────────────────────────────
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cysd_erp.settings')
django.setup()

from tracker.models import (
    Domain, Employee, Meeting, Project, Task,
)

# ── Reproducible randomness ───────────────────────────────────────────────────
random.seed(42)

TODAY = datetime.date.today()

def days_ago(n):
    return TODAY - datetime.timedelta(days=n)

def days_ahead(n):
    return TODAY + datetime.timedelta(days=n)

# ─────────────────────────────────────────────────────────────────────────────
# 1. DOMAINS
# ─────────────────────────────────────────────────────────────────────────────
DOMAIN_DATA = [
    {
        'name': 'Sustainable Rural Livelihoods',
        'code': 'SRL',
        'lead': 'Dr. Ananya Mishra',
        'description': (
            'Focuses on income generation, micro-enterprise development, '
            'and sustainable agricultural practices in rural Odisha.'
        ),
    },
    {
        'name': 'Governance & Panchayat Systems',
        'code': 'GPS',
        'lead': 'Mr. Rakesh Pradhan',
        'description': (
            'Strengthens grassroots democratic institutions, trains elected '
            'representatives, and improves transparency in local governance.'
        ),
    },
    {
        'name': 'Inclusive Education',
        'code': 'IED',
        'lead': 'Ms. Priya Nayak',
        'description': (
            'Promotes equitable access to quality education for marginalised '
            'children, adolescents, and first-generation learners.'
        ),
    },
    {
        'name': 'Women Empowerment & Micro-enterprises',
        'code': 'WEM',
        'lead': 'Ms. Sudha Rath',
        'description': (
            'Builds economic agency for women through SHG federations, skill '
            'training, and micro-credit linkages.'
        ),
    },
    {
        'name': 'Health & Nutrition',
        'code': 'HLN',
        'lead': 'Dr. Subhash Mohanty',
        'description': (
            'Addresses maternal-child health, malnutrition, WASH integration, '
            'and community health worker capacity building.'
        ),
    },
    {
        'name': 'Climate Resilience & Natural Resources',
        'code': 'CRN',
        'lead': 'Mr. Debasis Patra',
        'description': (
            'Supports watershed management, climate-adaptive farming, '
            'and community-based natural resource governance.'
        ),
    },
]

def seed_domains():
    if Domain.objects.exists():
        print('  [SKIP] Domains already present.')
        return list(Domain.objects.order_by('id'))

    created = []
    for d in DOMAIN_DATA:
        obj = Domain.objects.create(
            name=d['name'],
            code=d['code'],
            lead=d['lead'],
            description=d['description'],
            is_active=True,
        )
        created.append(obj)
    print(f'  [OK]   Created {len(created)} Domains.')
    return created


# ─────────────────────────────────────────────────────────────────────────────
# 2. EMPLOYEES
# ─────────────────────────────────────────────────────────────────────────────
EMPLOYEE_DATA = [
    # (name, gender, designation, employment_type, dob_year)
    ('Arjun Kumar Sahoo',       'M', 'Program Manager',           'full_time',    1985),
    ('Priyanka Das',            'F', 'Field Coordinator',          'full_time',    1990),
    ('Ramesh Chandra Behera',   'M', 'Policy Analyst',             'full_time',    1983),
    ('Sunita Panda',            'F', 'Research Associate',         'contractual',  1992),
    ('Bikash Nanda',            'M', 'Community Mobiliser',        'full_time',    1988),
    ('Mamata Tripathy',         'F', 'Senior Program Officer',     'full_time',    1980),
    ('Subrat Kumar Jena',       'M', 'Monitoring & Evaluation Officer', 'full_time', 1987),
    ('Lipika Mohanty',          'F', 'Livelihood Specialist',      'full_time',    1991),
    ('Santosh Sahu',            'M', 'District Coordinator',       'full_time',    1982),
    ('Anita Devi',              'F', 'Health Programme Officer',   'contractual',  1993),
    ('Pradeep Kumar Swain',     'M', 'Capacity Building Trainer',  'full_time',    1979),
    ('Kabita Senapati',         'F', 'Social Worker',              'volunteer',    1995),
    ('Dilip Rout',              'M', 'Finance & Accounts Officer', 'full_time',    1984),
    ('Sujata Mishra',           'F', 'Gender & Inclusion Analyst', 'full_time',    1989),
    ('Manoranjan Patel',        'M', 'Watershed Development Officer', 'full_time', 1981),
    ('Pratima Nayak',           'F', 'Education Programme Officer','full_time',    1994),
    ('Gautam Biswal',           'M', 'Field Research Intern',      'intern',       1999),
    ('Reena Kumari',            'F', 'Communications Officer',     'part_time',    1996),
    ('Ashok Kumar Parida',      'M', 'IT & Data Systems Officer',  'full_time',    1986),
    ('Sasmita Barik',           'F', 'Project Assistant',          'intern',       2000),
]

ODISHA_TOWNS = [
    'Bhubaneswar', 'Cuttack', 'Berhampur', 'Sambalpur', 'Rourkela',
    'Puri', 'Balasore', 'Bargarh', 'Koraput', 'Phulbani',
]

def seed_employees(domains):
    if Employee.objects.exists():
        print('  [SKIP] Employees already present.')
        return list(Employee.objects.order_by('id'))

    created = []
    domain_cycle = domains * 4   # ensure enough to distribute

    for idx, (name, gender, designation, emp_type, dob_yr) in enumerate(EMPLOYEE_DATA, start=1):
        emp_id   = f'CYSD-2024-{idx:03d}'
        # Derive email: firstname.lastname@cysd.org (lowercase, no spaces)
        parts    = name.lower().split()
        email    = f'{parts[0]}.{parts[-1]}@cysd.org'
        phone    = f'+91 9{random.randint(100000000, 999999999)}'
        town     = random.choice(ODISHA_TOWNS)
        address  = f'{random.randint(1,200)}, {random.choice(["Gandhi Nagar","Civil Lines","Sector","MG Road","Station Road"])}, {town}, Odisha'
        dob      = datetime.date(dob_yr, random.randint(1, 12), random.randint(1, 28))
        joined   = days_ago(random.randint(180, 2000))
        domain   = domain_cycle[idx - 1]

        obj = Employee.objects.create(
            employee_id     = emp_id,
            name            = name,
            gender          = gender,
            date_of_birth   = dob,
            domain          = domain,
            designation     = designation,
            employment_type = emp_type,
            date_joined     = joined,
            is_active       = True,
            email           = email,
            phone           = phone,
            address         = address,
            notes           = f'Seeded record — {designation} in {domain.name}.',
        )
        created.append(obj)

    print(f'  [OK]   Created {len(created)} Employees.')
    return created


# ─────────────────────────────────────────────────────────────────────────────
# 3. PROJECTS
# ─────────────────────────────────────────────────────────────────────────────
PROJECT_TEMPLATES = [
    # (title, domain_code, start_offset_days_ago, deadline_offset_days_ahead, status)
    ('Odisha Village Micro-enterprise Scale-up Initiative',   'SRL', 120, 90,  'active'),
    ('Panchayat Governance Capacity Building Programme',      'GPS', 200, 60,  'active'),
    ('Rural Digital Literacy Campaign – Phase II',            'IED', 90,  120, 'active'),
    ('Women-Led SHG Federation Strengthening Project',        'WEM', 150, 45,  'active'),
    ('Community Nutrition & WASH Integration Programme',      'HLN', 180, 75,  'active'),
    ('Watershed Rejuvenation & Climate Adaptive Farming',     'CRN', 100, 150, 'planning'),
    ('Right to Education Outreach – Tribal Blocks',           'IED', 30,  180, 'planning'),
    ('Micro-credit & Market Linkage for Rural Artisans',      'SRL', 300, 30,  'completed'),
    ('District-level Governance Audit & Feedback Initiative', 'GPS', 400, 10,  'delayed'),
    ('Adolescent Health & Menstrual Hygiene Campaign',        'HLN', 60,  200, 'active'),
]

def seed_projects(domains, employees):
    if Project.objects.exists():
        print('  [SKIP] Projects already present.')
        return list(Project.objects.order_by('id'))

    domain_map = {d.code: d for d in domains}
    created = []

    for title, dcode, start_ago, dl_ahead, status in PROJECT_TEMPLATES:
        domain = domain_map.get(dcode)
        lead   = random.choice(employees)

        obj = Project.objects.create(
            title         = title,
            domain        = domain,
            start_date    = days_ago(start_ago),
            deadline      = days_ahead(dl_ahead),
            status        = status,
            lead_employee = lead,
        )
        created.append(obj)

    print(f'  [OK]   Created {len(created)} Projects.')
    return created


# ─────────────────────────────────────────────────────────────────────────────
# 4. MEETINGS
# ─────────────────────────────────────────────────────────────────────────────
MEETING_TEMPLATES = [
    # (title, domain_code, meeting_type, intervention_scale, days_offset)
    # Negative = past, Positive = future
    ('Quarterly Programme Review – SRL Domain',               'SRL', 'internal',  'district',   -90),
    ('Field Assessment: Micro-enterprise Clusters in Koraput','SRL', 'field',     'community',  -75),
    ('Partner Coordination Meet – NABARD & SIDBI',            'SRL', 'partner',   'state',      -60),
    ('SHG Leaders Skill Training Workshop',                   'WEM', 'training',  'community',  -55),
    ('Board Review: Women Empowerment Fund Disbursement',     'WEM', 'board',     'state',      -50),
    ('Panchayat Representatives Governance Training',         'GPS', 'training',  'district',   -45),
    ('State-Level Policy Advocacy Roundtable',                'GPS', 'partner',   'state',      -40),
    ('Gram Sabha Monitoring & Feedback Session',              'GPS', 'field',     'community',  -35),
    ('School Enrolment Drive Planning Meeting',               'IED', 'internal',  'district',   -30),
    ('Tribal Block Education Outreach Review',                'IED', 'field',     'community',  -28),
    ('ASER Learning Assessment Workshop',                     'IED', 'training',  'district',   -25),
    ('VHSNC Monthly Health Review',                           'HLN', 'internal',  'community',  -22),
    ('Maternal & Child Nutrition Campaign Planning',          'HLN', 'partner',   'district',   -20),
    ('WASH Infrastructure Field Verification Visit',          'HLN', 'field',     'community',  -18),
    ('National Health Mission Coordination Meeting',          'HLN', 'partner',   'national',   -15),
    ('Watershed Development Baseline Survey Review',          'CRN', 'internal',  'district',   -12),
    ('Climate Resilience Farmers\' Field School',             'CRN', 'training',  'community',  -10),
    ('Annual Programme Impact Assessment',                    'SRL', 'board',     'state',       -8),
    ('Individual Beneficiary Tracking Session – Koraput',     'SRL', 'internal',  'individual',  -6),
    ('Mid-Term Review: Micro-enterprise Project',             'WEM', 'internal',  'district',    -5),
    ('State Gender Mainstreaming Consultative Meet',          'WEM', 'partner',   'state',       -3),
    ('Board Meeting – Q3 Financial & Programme Review',       'GPS', 'board',     'national',    -2),
    ('Panchayat IT Systems Training',                         'GPS', 'training',  'district',    -1),
    ('Education Budget Advocacy Preparation',                 'IED', 'internal',  'state',        1),
    ('Community Health Workers Monthly Debrief',              'HLN', 'internal',  'community',    3),
    ('MNREGA-Watershed Convergence Planning',                 'CRN', 'partner',   'district',     5),
    ('SRL Domain Q4 Planning Workshop',                       'SRL', 'internal',  'district',     7),
    ('National Rural Livelihoods Mission Partner Meet',       'SRL', 'partner',   'national',    10),
    ('Right to Education Compliance Review',                  'IED', 'internal',  'state',       14),
    ('Women Entrepreneur Mentoring Circle',                   'WEM', 'training',  'individual',  18),
    ('District Nutrition Convergence Meeting',                'HLN', 'partner',   'district',    21),
    ('Panchayat Finance & Audit Training',                    'GPS', 'training',  'community',   25),
    ('Annual Stakeholder Report Presentation',                'SRL', 'board',     'national',    30),
    ('Climate Adaptive Agriculture State Conference',         'CRN', 'partner',   'state',       35),
    ('Individual Household Livelihood Planning Session',      'SRL', 'field',     'individual',  40),
]

VENUES = [
    'CYSD Head Office, Bhubaneswar',
    'District Collectorate Conference Hall, Koraput',
    'Block Development Office, Phulbani',
    'Panchayat Samiti Hall, Bargarh',
    'Community Resource Centre, Nabarangpur',
    'DRDA Conference Room, Balangir',
    'Hotel Swosti, Bhubaneswar',
    'OUAT Auditorium, Bhubaneswar',
    'Zoom Video Call',
    'Google Meet (Online)',
    'Village Community Hall, Malkangiri',
    'District Education Office, Rayagada',
]

AGENDA_SNIPPETS = [
    '1. Review of progress against last quarter targets\n2. Field observation findings\n3. Budget utilisation update\n4. Next steps and action planning',
    '1. Opening remarks by Programme Head\n2. Presentation of baseline data\n3. Stakeholder feedback round\n4. Resource mobilisation discussion\n5. Closure and vote of thanks',
    '1. Policy alignment review\n2. Cross-domain convergence opportunities\n3. Partner coordination updates\n4. Risk and challenge identification\n5. Action point finalisation',
    '1. Beneficiary status update\n2. Field coordinator reports\n3. Data quality review\n4. Documentation gaps\n5. Next field visit scheduling',
    '1. Training module review\n2. Participant skill assessment results\n3. Feedback from community members\n4. Revision of training calendar\n5. Resource requirements',
]

MINUTES_SNIPPETS = [
    'The meeting commenced at the scheduled time. All agenda items were discussed in detail. Field coordinators presented progress reports showing 78% achievement of quarterly targets. Key challenges identified included delayed fund disbursement and seasonal migration of beneficiaries. The team agreed to escalate fund release to the finance department.',
    'Participants reviewed the baseline survey findings. Data showed significant gaps in access to services in 3 target blocks. A sub-committee was formed to develop a remediation plan. Partner organisations confirmed availability of technical support. The next review meeting was scheduled for the following month.',
    'The programme head opened the session by highlighting the strategic importance of inter-departmental convergence. Field reports were presented by all domain coordinators. Community feedback was largely positive with requests for more frequent training sessions. Budget reallocation of INR 2.5 lakhs was approved for accelerated field activities.',
    'Attended by 12 participants including government officials and CSO representatives. The monitoring data was reviewed and validated. Three action points from the previous meeting were found to be completed. Two points remain pending due to infrastructure delays. A revised timeline was agreed upon.',
    'The training session covered practical modules on participatory rural appraisal tools and community mapping. Participants demonstrated improved competency in data collection methodologies. Feedback forms indicated 89% satisfaction rate. Materials will be translated into Odia for wider distribution.',
]

def seed_meetings(domains, employees):
    if Meeting.objects.exists():
        print('  [SKIP] Meetings already present.')
        return list(Meeting.objects.order_by('id'))

    domain_map = {d.code: d for d in domains}
    created = []

    for title, dcode, mtype, scale, day_offset in MEETING_TEMPLATES:
        mtg_date = TODAY + datetime.timedelta(days=day_offset)
        is_past  = day_offset < 0

        # Status logic: past meetings are completed/cancelled, future are scheduled/postponed
        if is_past:
            status = random.choices(
                ['completed', 'completed', 'completed', 'cancelled'],
                weights=[7, 7, 7, 3],
            )[0]
        else:
            status = random.choices(
                ['scheduled', 'scheduled', 'postponed'],
                weights=[8, 8, 2],
            )[0]

        start_hour  = random.choice([9, 10, 11, 14, 15])
        start_time  = datetime.time(start_hour, 0)
        end_time    = datetime.time(start_hour + random.choice([1, 2]), 30)
        organiser   = random.choice(employees)
        attendee_sample = random.sample(employees, k=random.randint(3, 8))

        obj = Meeting.objects.create(
            title              = title,
            domain             = domain_map.get(dcode),
            meeting_type       = mtype,
            status             = status,
            intervention_scale = scale,
            date               = mtg_date,
            start_time         = start_time,
            end_time           = end_time,
            venue              = random.choice(VENUES),
            agenda             = random.choice(AGENDA_SNIPPETS),
            minutes            = random.choice(MINUTES_SNIPPETS) if is_past else '',
            action_points      = (
                '- Follow up on fund release by finance team\n'
                '- Share field reports with M&E officer by next Friday\n'
                '- Schedule next community visit within 2 weeks'
            ) if is_past else '',
            organised_by       = organiser.name,
        )
        obj.attendees.set(attendee_sample)
        created.append(obj)

    print(f'  [OK]   Created {len(created)} Meetings.')
    return created


# ─────────────────────────────────────────────────────────────────────────────
# 5. TASKS
# ─────────────────────────────────────────────────────────────────────────────
TASK_TITLE_POOL = [
    'Conduct baseline household survey in target village',
    'Prepare quarterly progress report for donor',
    'Facilitate SHG weekly meeting and record minutes',
    'Map beneficiaries using GPS and household forms',
    'Develop training curriculum for community health workers',
    'Liaise with Block Development Officer on convergence plan',
    'Compile field photographs and geo-tagged evidence',
    'Submit financial utilisation certificate to accounts',
    'Conduct FGD with women beneficiaries on enterprise outcomes',
    'Coordinate with NABARD for credit linkage documentation',
    'Review and validate M&E data entry in MIS portal',
    'Organise inter-village exposure visit for SHG members',
    'Draft policy brief on Panchayat budget transparency',
    'Train Gram Panchayat members on RTI filing procedures',
    'Conduct school dropout identification survey',
    'Distribute learning kits to enrolled tribal children',
    'Monitor construction progress of WASH infrastructure',
    'Prepare case studies of successful livelihood interventions',
    'Collect and analyse ASER learning assessment data',
    'Facilitate community watershed planning meeting',
    'Document traditional farming knowledge for curriculum',
    'Verify attendance registers for training programme',
    'Prepare procurement plan for next quarter',
    'Conduct staff capacity needs assessment',
    'Develop social media content on programme impact',
    'Coordinate with District Education Officer on campaign',
    'Submit reimbursement claims and travel bills',
    'Conduct nutrition screening of children under 5',
    'Facilitate inter-departmental convergence meeting notes',
    'Draft MoU with partner organisation for co-implementation',
]

# Status weights designed to stress-test the efficiency calculation:
# ~35% completed, ~30% in_progress, ~20% pending, ~15% overdue
TASK_STATUS_WEIGHTS = {
    'completed':  35,
    'in_progress': 30,
    'pending':     20,
    'overdue':     15,
}

def seed_tasks(projects, employees, target=90):
    if Task.objects.exists():
        print('  [SKIP] Tasks already present.')
        return Task.objects.count()

    statuses = list(TASK_STATUS_WEIGHTS.keys())
    weights  = list(TASK_STATUS_WEIGHTS.values())

    created = 0
    tasks_per_project = target // len(projects)
    remainder         = target % len(projects)

    for p_idx, project in enumerate(projects):
        count = tasks_per_project + (1 if p_idx < remainder else 0)

        for _ in range(count):
            status = random.choices(statuses, weights=weights)[0]

            # Due dates: overdue tasks must be in the past
            if status == 'overdue':
                due = days_ago(random.randint(5, 60))
            elif status == 'completed':
                due = days_ago(random.randint(1, 90))
            elif status == 'in_progress':
                due = days_ahead(random.randint(1, 45))
            else:  # pending
                due = days_ahead(random.randint(7, 120))

            # Hours logged: completed tasks have the most, overdue some, pending zero
            if status == 'completed':
                hours = Decimal(str(round(random.uniform(4.0, 40.0), 2)))
            elif status == 'in_progress':
                hours = Decimal(str(round(random.uniform(1.0, 20.0), 2)))
            elif status == 'overdue':
                hours = Decimal(str(round(random.uniform(0.5, 15.0), 2)))
            else:
                hours = Decimal('0.00')

            Task.objects.create(
                title       = random.choice(TASK_TITLE_POOL),
                project     = project,
                assigned_to = random.choice(employees),
                due_date    = due,
                status      = status,
                hours_logged= hours,
            )
            created += 1

    print(f'  [OK]   Created {created} Tasks.')
    return created


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print('\n' + '=' * 58)
    print('  CYSD ERP — Seed Data Script')
    print('=' * 58)

    print('\n[1/5] Seeding Domains...')
    domains = seed_domains()

    print('\n[2/5] Seeding Employees...')
    employees = seed_employees(domains)

    print('\n[3/5] Seeding Projects...')
    projects = seed_projects(domains, employees)

    print('\n[4/5] Seeding Meetings...')
    seed_meetings(domains, employees)

    print('\n[5/5] Seeding Tasks...')
    seed_tasks(projects, employees, target=90)

    print('\n' + '=' * 58)
    print('  Final record counts in database:')
    print(f'    Domains   : {Domain.objects.count()}')
    print(f'    Employees : {Employee.objects.count()}')
    print(f'    Projects  : {Project.objects.count()}')
    print(f'    Meetings  : {Meeting.objects.count()}')
    print(f'    Tasks     : {Task.objects.count()}')
    print('=' * 58)
    print('  Seed complete.\n')


main()
