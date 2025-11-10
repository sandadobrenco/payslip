# Payroll / Payslip App (Django REST + Celery)

Automates payroll for managers: calculate salaries, generate employee payslips (PDF), export team summaries (CSV), and send them by email — securely and with role-based access.

---

## ✨ Features

* **Role-based access**: Top Manager (full access) vs Manager (self + direct reports).
* **Employees**: CRUD with safe defaults (password write-only, computed fields read-only).
* **Payroll periods**: month-based windows used for calculations.
* **Compensation & bonuses**: base salary (one per user) + optional period bonuses.
* **Attendance**: daily records used in salary proration.
* **Reports**: per-employee **PDF payslip** and **CSV** team export.
* **Email delivery**: send PDF/CSV via SMTP.

---

## 🏗️ Stack

* **Backend**: Python, Django , Django REST Framework
* **DB**: PostgreSQL
* **Async**: Celery + Redis
* **Packaging**: Docker & Docker Compose
* **Storage**: `MEDIA_ROOT` for generated `pdf/`, `csv/`, `archives/`

---

## 🔐 Roles & Permissions (high level)

* **Top Manager**: can view/edit everyone; can set an employee’s `manager`.
* **Manager**: can view/edit only self + direct reports; cannot change `manager` field (ignored on update). Querysets are restricted: out‑of‑scope objects return **404**.

**Trailing slash**: project uses `APPEND_SLASH=True`. Use `/endpoint/` (with `/`).

---

## ⚙️ Quickstart (Docker)

1. **Clone & prepare**

   ```bash
   git clone https://github.com/<you>/<repo>.git
   ```
2. **Start services**

   ```bash
   docker compose up --build
   ```
3. **Apply migrations & create admin**

   ```bash
   docker compose exec app python manage.py migrate
   docker compose exec app python manage.py createsuperuser
   ```
4. **Open API**: `http://localhost:8000/` (browseable DRF)
   **Admin**: `http://localhost:8000/admin/`

---

## 🔑 Environment (.env)

Copy from `.env.example` and adjust:

```dotenv
# Django
DJANGO_DEBUG=True
DJANGO_SECRET_KEY=change-me

# DB
POSTGRES_DB=salary_db
POSTGRES_USER=salary_user
POSTGRES_PASSWORD=change-me
POSTGRES_HOST=postgres_db
POSTGRES_PORT=5432

# Email (choose one: Gmail or Mailpit)
# --- Gmail (real emails) ---
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=you@gmail.com
EMAIL_HOST_PASSWORD=<GOOGLE_APP_PASSWORD_16>
DEFAULT_FROM_EMAIL=you@gmail.com
EMAIL_FROM_NAME=Payroll System
EMAIL_TIMEOUT=30

# --- Mailpit (local sandbox) ---
#EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
#EMAIL_HOST=mailpit
#EMAIL_PORT=1025
#EMAIL_USE_TLS=False
#DEFAULT_FROM_EMAIL=hr@local.dev
```

> **Gmail** requires 2‑step verification and an **App Password** (16 chars).
> **Mailpit** is recommended for local testing (add a `mailpit` service in compose and open `http://localhost:8025`).

---

## 📚 Data Model (key concepts)

* **User**: `is_manager` flag; `manager` FK (hierarchy). Password is **write‑only**.
* **PayrollPeriod**: (`year`, `month`, derived `start_date`, `end_date`, lock flags).
* **Compensation**: base monthly amount per user (exactly one active record per user).
* **Bonus** *(optional)*: period‑bound additions.
* **Attendance**: daily entries; current proration uses *business days − unpaid leave* (see below).

**Current proration logic**: payslip assumes full business days (Mon–Fri) in the period and subtracts only **UNPAID_LEAVE** days. If you log only 1 worked day but do not mark the rest as unpaid leave, the system treats the month as fully paid. (Roadmap: switch to *paid days* model.)

---
