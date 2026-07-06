# CYSD ERP Dashboard

Enterprise Resource Planning dashboard for **CYSD** (Centre for Youth and Social Development), built with Django 4.2 and PostgreSQL.

---

## Quick Start

### 1. Prerequisites

- Python 3.10+
- PostgreSQL 14+
- Git

### 2. Clone and set up virtual environment

```bash
git clone <repo-url>
cd cysd-erp

python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
copy .env.example .env       # Windows
cp .env.example .env         # macOS / Linux
```

Edit `.env` and set your PostgreSQL credentials and a strong `SECRET_KEY`.

### 5. Create the PostgreSQL database

```sql
-- Run in psql or pgAdmin
CREATE DATABASE cysd_erp_db;
```

### 6. Run migrations

```bash
python manage.py migrate
```

### 7. Create a superuser (admin access)

```bash
python manage.py createsuperuser
```

### 8. Create static/media directories and collect static files

```bash
mkdir static staticfiles media
python manage.py collectstatic --noinput
```

### 9. Start the development server

```bash
python manage.py runserver
```

Open **http://127.0.0.1:8000/admin/** and log in with the superuser credentials.

---

## Data Entry via Admin

Once logged in to `/admin/`:

| Model | What to enter |
|-------|---------------|
| **Domain** | Create NGO programme areas first (e.g. Education, Health). Each needs a name, short code, and lead name. |
| **Employee** | Add staff/volunteers. Select their domain, fill designation, employment type, and contact info. |
| **Meeting** | Log meetings linked to a domain. Add attendees from the Employee list, record agenda, minutes, and action points. |

### Admin features

- **Domain list** – Inline toggle for `is_active`, active staff count badge, bulk activate/deactivate actions.
- **Employee list** – Filter by domain, employment type, gender. Photo preview in edit form. Bulk activate/deactivate.
- **Meeting list** – Colour-coded status badges (blue = Scheduled, green = Completed, red = Cancelled, orange = Postponed). Dual-pane attendee selector. Bulk mark-complete/cancel actions.

---

## Project Structure

```
cysd-erp/
├── cysd_erp/               # Django project package
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── tracker/                # Main app
│   ├── models.py           # Domain, Employee, Meeting
│   ├── admin.py            # Admin configurations
│   ├── views.py            # Dashboard view
│   ├── urls.py
│   └── migrations/
│       └── 0001_initial.py
├── static/                 # Source static files (CSS, JS, images)
├── staticfiles/            # Collected static files (generated)
├── media/                  # Uploaded media (photos, attachments)
├── templates/              # HTML templates
├── manage.py
├── requirements.txt
└── .env.example
```

---

## Tech Stack

| Component | Version |
|-----------|---------|
| Django | 4.2.13 |
| PostgreSQL | 14+ |
| psycopg2-binary | 2.9.9 |
| python-decouple | 3.8 |
| Pillow | 10.3.0 |
| django-crispy-forms | 2.1 |
| crispy-bootstrap5 | 0.7 |
| whitenoise | 6.6.0 |
