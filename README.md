# CYSD ERP Dashboard

Enterprise Resource Planning dashboard for **CYSD** (Centre for Youth and Social Development), built with Django 4.2, PostgreSQL, Pandas, and Chart.js.

---

## Features

### 1. Multi-Tenant Subdomain Architecture
The system supports multiple distinct tenant organizations (Enterprises) running on a single deployment. Tenants are isolated at the routing and database levels:
* Routing resolved dynamically based on subdomains (e.g., `cysd.localhost` vs `rasayam.localhost`).
* Middleware boundary checks enforce that users can only log in to their assigned enterprise workspace.

### 2. Role-Based Access Control (RBAC)
Granular, role-based controls protect views and restrict operations. Supported roles include:
* **Founder**: Executive dashboard access with organization-wide visibility and task assignment.
* **HR**: Manage employees, domains, and core configurations. Sensitive meeting information (agendas, minutes) is masked.
* **Supervisor**: Scope limited to their direct subordinates. Can create and resolve checklist tasks.
* **Employee / Intern / Volunteer**: Access to a personal workspace ("My Tasks") to track deliverables and log hours.

### 3. Task Checklist Approval Workflow
Implements a state machine for task verification and supervisor sign-offs:
```
       [Supervisor assigns item]
                  │
                  ▼
            ┌───────────┐
            │  PENDING  │ ◄──────────────────────────┐
            └─────┬─────┘                            │
                  │                                  │
       [Employee marks as Done]              [Supervisor Rejects]
                  │                                  │
                  ▼                                  │
     ┌─────────────────────────┐                     │
     │  AWAITING_VERIFICATION  ├─────────────────────┘
     └────────────┬────────────┘
                  │
         [Supervisor Approves]
                  │
                  ▼
            ┌───────────┐
            │ COMPLETED │ ──► (Triggers atomic EmployeeStats refresh)
            └───────────┘
```

### 4. Cached Aggregates & Analytics
* **EmployeeStats**: Atomically recalculated performance metrics snapshot for every employee. Aggregated metrics (completion rates, task ratios) are stored in this table to serve dashboards instantly, avoiding expensive database joins on every load.
* **Interactive Dashboards**: Dynamic charts representing workload statistics and policy intervention scales rendered using Pandas and Matplotlib/Chart.js.

---

## Database Schema & Relationships

The database comprises **9 core models**:

| Model | Description | Key Relationships |
| :--- | :--- | :--- |
| **Enterprise** | Represents the tenant organization. | *Tenant Root* |
| **Domain** | Thematic NGO program area (e.g., Education). | `ForeignKey` ──► `Enterprise` |
| **Employee** | Profiles for staff members/volunteers. Handles RBAC. | `ForeignKey` ──► `Enterprise`<br>`OneToOne` ──► Django `User`<br>`ForeignKey` ──► `self` (Supervisor)<br>`ForeignKey` ──► `Domain` |
| **Meeting** | Meeting logs containing attendee and action details. | `ForeignKey` ──► `Enterprise`<br>`ForeignKey` ──► `Domain`<br>`ManyToMany` ──► `Employee` (Attendees) |
| **Project** | NGO projects with deadlines and progress states. | `ForeignKey` ──► `Enterprise`<br>`ForeignKey` ──► `Domain`<br>`ForeignKey` ──► `Employee` (Lead) |
| **Task** | Deliverables associated with specific projects. | `ForeignKey` ──► `Enterprise`<br>`ForeignKey` ──► `Project`<br>`ManyToMany` ──► `Employee` (Assigned To) |
| **TaskChecklist** | Multi-phase task checklists needing verification. | `ForeignKey` ──► `Enterprise`<br>`ForeignKey` ──► `Employee` (Assigned To)<br>`ForeignKey` ──► `Employee` (Created By) |
| **EmployeeStats** | Cached performance analytics snapshot. | `OneToOne` ──► `Employee` (Primary Key) |
| **User** | Django authentication model. | Mapped to `Employee` |

---

## RBAC Permission Matrix

| Operation / Feature | Founder | HR | Supervisor | Employee | Intern | Volunteer |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Setup Enterprise Configuration** | ✔ | ✔ | ✘ | ✘ | ✘ | ✘ |
| **Manage Domains & Structure** | ✔ | ✔ | ✘ | ✘ | ✘ | ✘ |
| **Manage Employee Registry** | ✔ | ✔ | ✘ | ✘ | ✘ | ✘ |
| **View Confidential Meeting Details** | ✔ | ✘ | ✔ | ✔ | ✔ | ✔ |
| **Export Meeting CSV Reports** | ✔ | ✔ | ✔ | ✘ | ✘ | ✘ |
| **Assign Task Checklist Items** | ✔ | ✔ | Subordinates | ✘ | ✘ | ✘ |
| **Verify/Resolve Task Checklists** | ✔ | ✔ | Subordinates | ✘ | ✘ | ✘ |
| **Log Hours & Complete Tasks** | ✘ | ✘ | ✘ | ✔ | ✔ | ✔ |

---

## Requirements & Stack

| Dependency | Version | Purpose |
| :--- | :--- | :--- |
| **Django** | `4.2.30` | Core Web Framework (Long-Term Support) |
| **django-unfold** | `0.28.0` | Modern Django admin theme |
| **psycopg2-binary** | `2.9.12` | PostgreSQL database adapter |
| **python-decouple** | `3.8` | Configuration settings parser |
| **Pillow** | `12.2.0` | Image validation and photo storage |
| **django-crispy-forms** | `2.1` | Bootstrap form rendering |
| **crispy-bootstrap5** | `0.7` | Bootstrap 5 layout integration |
| **whitenoise** | `6.6.0` | Production static files server |
| **django-filter** | `24.3` | Advanced registry table filtering |
| **pandas** | `3.0.3` | Analytics dataframes & aggregation |
| **matplotlib** | `3.11.0` | Headless chart generation |
| **django-environ** | `0.13.0` | Twelve-factor configuration helper |
| **gunicorn** | `22.0.0` | WSGI Production Web server |
| **argon2-cffi** | `25.1.0` | High-security password hashing |

---

## Local Setup & Subdomain Configuration

### 1. Prerequisites
* Python 3.10+
* PostgreSQL 14+

### 2. Configure Local Host Routing
To test multi-tenant subdomain routing on your local machine, map the subdomains to `localhost` in your hosts file:
* **Windows**: Add to `C:\Windows\System32\drivers\etc\hosts`
* **macOS / Linux**: Add to `/etc/hosts`

```text
127.0.0.1 cysd.localhost
127.0.0.1 rasayam.localhost
```

### 3. Setup Virtual Environment & Install
```bash
py -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 4. Database Setup
1. Create a PostgreSQL database:
   ```sql
   CREATE DATABASE cysd_erp_db;
   ```
2. Copy `.env.example` to `.env` and fill in credentials:
   ```bash
   copy .env.example .env
   ```
3. Run migrations and seed command:
   ```bash
   py manage.py migrate
   py manage.py setup_test_tenants
   ```

### 5. Running Server
```bash
py manage.py runserver
```
Navigate to:
* **CYSD Workspace**: [http://cysd.localhost:8000/dashboard/](http://cysd.localhost:8000/dashboard/)
* **Rasayam Workspace**: [http://rasayam.localhost:8000/dashboard/](http://rasayam.localhost:8000/dashboard/)

---

## Developer Experience: Dev-Switch Masquerader

For rapid local testing of role-based features without constantly logging in and out, the application includes a **Masquerade Endpoint**:
* **Endpoint**: `/dashboard/dev-switch/<role_name>/` (Roles: `founder`, `hr`, `supervisor`, `employee`).
* **Security Guard**: This endpoint is protected by a strict check on `settings.DEBUG`. If the project is running with `DEBUG=False` (production), the view immediately returns a `403 Forbidden` response.
