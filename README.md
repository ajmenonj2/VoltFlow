# VoltFlow — EV Charging Station Management System

A working DBMS project built from the group's existing VoltFlow UI and database design. It uses **Flask (Python) + SQLite SQL** so it runs locally without installing a separate database server. The schema uses primary keys, foreign keys, `UNIQUE`, `CHECK`, and indexes. The frontend retains the dark-purple dashboard style and connects to real API endpoints.

## Features implemented

- Login/logout with hashed passwords and role-based access; EV owner self-registration.
- Dashboard statistics generated from SQL data, including stations, available chargers, sessions, energy and paid revenue.
- Station creation creates its charger records in the same transaction.
- Vehicle registration with ownership enforcement.
- Reservations with vehicle ownership validation, future-time validation and same-station/same-slot conflict checking; reservation cancellation.
- Start charging for a confirmed reservation, automatically assigning an available charger.
- Complete charging with kWh input, duration calculation, charger release, reservation completion and automatic bill generation using station tariff.
- Payment listing and payment status updates.
- Maintenance scheduling, technician assignment and status workflow.
- Reports for station usage and monthly paid revenue.
- Parameterized SQL, foreign-key enforcement, password hashing, API-side authorization and validation.

## Run it

Requires Python 3.10 or newer.

```bash
cd voltflow_project
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000

### Demo accounts

- Admin: `admin@voltflow.in` / `Admin@123`
- EV Owner: `owner@voltflow.in` / `Owner@123`
- Maintenance technician: `tech@voltflow.in` / `Tech@123`

Change demo passwords and the Flask `SECRET_KEY` before any deployment. The application is a college-project prototype, not a production payment gateway or charger hardware integration.

## Suggested demo sequence

1. Log in as Admin and inspect Dashboard and Stations.
2. Log in as EV Owner, register a vehicle, then create a reservation for a future time.
3. Log in as Admin, open Reservations, then Charging; start a session for that confirmed reservation.
4. Complete the session and enter an energy value. The system calculates the bill using the station's ₹/kWh tariff.
5. Open Payments and mark the generated payment as paid.
6. Open Maintenance and create/update a maintenance record; open Reports to see SQL-derived results.

## Project structure

- `app.py` — Flask routes, authentication, validation, SQL operations, seed data.
- `templates/index.html` — responsive frontend and client-side API calls.
- `schema.sql` — relational schema for DBMS documentation/review.
- `requirements.txt` — Python dependency.
- `voltflow_original.html` — untouched copy of the uploaded original UI for reference.

## Database design alignment

The original design's eight entities are represented by `users`, `vehicles`, `charging_stations`, `chargers`, `reservations`, `charging_sessions`, `payments`, and `maintenance_records`. `users.email` is a candidate key and unique; `user_id` is the surrogate primary key. A reservation can have at most one session (`UNIQUE reservation_id`), and a session can have at most one payment (`UNIQUE session_id`).

## Important scope limits

- The database is SQLite for easy setup; it is SQL and enforces relational constraints. If your instructor explicitly requires MySQL Server, the schema needs small dialect changes (for example, `AUTOINCREMENT` and date functions).
- Payments are simulated status records; no real money is charged.
- Charger availability updates are application-level prototype logic; no physical charger/IoT integration is included.
- Same exact slot conflict is checked; this is not a full time-duration/overlapping-slot scheduler.
- For real deployment, add CSRF protection, rate limiting, HTTPS, stronger secrets, migrations, audit logs and a proper production server.
