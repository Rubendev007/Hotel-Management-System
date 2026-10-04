# Hotel Management System (HMS)

A web-based hotel management platform built with Django, Python, and Bootstrap. HMS provides role-based workflows for administrators, receptionists, staff, housekeeping, and guests, including room booking, guest service requests, NPR (Rs.) price displays, and operational dashboards.

## Prerequisites

- Python 3.12 or newer (the project was checked with Python 3.14)
- Git
- `pip` (included with standard Python installations)
- Python's built-in `venv` module

The application currently uses SQLite for local development, so a separate database server is not required.

## Set up and run locally

Run the commands below from a terminal. The Django project and `manage.py` are in the repository's `HMS` subdirectory.

### 1. Clone the repository

```bash
git clone https://github.com/Rubendev007/Hotel-Management-System.git
cd Hotel-Management-System/HMS
```

If you already have a local copy, change to its `HMS` directory (the directory containing `manage.py`).

### 2. Create and activate a virtual environment

**Windows PowerShell:**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Windows Command Prompt:**

```bat
python -m venv venv
venv\Scripts\activate.bat
```

**macOS/Linux:**

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

There is currently no `requirements.txt` in the repository. Install the application dependencies with:

```bash
python -m pip install Django 'django-phonenumber-field[phonenumbers]' Pillow
```

`django-phonenumber-field` provides the phone number model field, its `phonenumbers` extra supports international phone-number validation, and Pillow is needed for Django image fields.

### 4. Apply database migrations

From the `HMS` directory, run:

```bash
python manage.py makemigrations
python manage.py migrate
```

The repository includes migrations for its applications. `makemigrations` is generally only needed when you have made model changes; `migrate` creates or updates the local SQLite database.

### 5. Create a Django admin superuser

```bash
python manage.py createsuperuser
```

This creates an account for Django's built-in administration site at `/admin/`. Application dashboards also use HMS role groups (such as `admin`, `receptionist`, `staff`, `housekeeping`, and `guest`); a Django superuser does not automatically select an HMS dashboard role. Assign users to the appropriate group when managing accounts.

### 6. Start the development server

```bash
python manage.py runserver
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) in your browser. The Django admin is at [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/).

For local development, Django uses SQLite in `HMS/db.sqlite3`, serves media from the configured local media directory, and prints outgoing email to the terminal. The development settings (`DEBUG = True`) are not suitable for production.

## Roles and dashboards

| Role | Main entry point | Typical workflows |
| --- | --- | --- |
| Admin | `/dashboard/` | Operational dashboard, rooms, bookings, guests, employees, room services, announcements, and refunds. Django's built-in admin is available separately at `/admin/`. |
| Receptionist | `/rooms/` | Room availability console, guest lookup, express check-in, bookings, and room information. |
| Staff | `/staff/dashboard/` | View and process active food and maintenance service requests. |
| Housekeeping | `/housekeeping/` | View cleaning tasks, start cleaning, mark rooms clean, and manage housekeeping work. |
| Guest | `/guest/dashboard/` | View the current reservation and dashboard, browse rooms, book a room, manage profile/bookings, and request room services. |

Guests can register at `/register/` and sign in at `/login/`. Additional workflows include `/rooms/` for the room catalog, `/my-room/` for a guest's current room booking, and `/current-room-services/` for guest service requests.

## Contributing

After making changes, run the Django checks and relevant tests from the `HMS` directory:

```bash
python manage.py check
python manage.py test
```

Create new migrations when you change models, and include those migration files with your changes.

## Sensitive data

Do not commit API keys, production credentials, local database credentials, or a production `SECRET_KEY` to a public repository. Use environment variables or an appropriately protected local configuration for secrets. The project reads `DJANGO_SECRET_KEY` from the environment; set a stable, securely generated value for deployments. Never deploy with `DEBUG = True`.
