# Simple CRM

A lightweight CRM platform built with FastAPI, Next.js, and PostgreSQL. Manages contacts, companies, deals, tasks, activities, and integrates with Gmail for email sync and tracking.

## Quick Start

### Prerequisites

- Docker and Docker Compose

### 1. Configure environment

```bash
cp .env.example .env
```

Generate a real secret key and set it in `.env`:

```bash
# Generate a secure key
openssl rand -hex 32

# Then edit .env and replace the SECRET_KEY value
```

The app **will not start** if `SECRET_KEY` is left as the default placeholder.

### 2. Start the stack

```bash
docker compose up -d
```

This starts three services:
- **PostgreSQL 17** — database
- **FastAPI backend** — `http://localhost:8000`
- **Next.js frontend** — `http://localhost:3000`

Tables are auto-created on first startup.

### 3. Bootstrap the admin user

On first startup, if no admin user exists, one is created automatically:

- **Email:** `admin@local.dev`
- **Password:** set via `ADMIN_PASSWORD` env var, or auto-generated

If `ADMIN_PASSWORD` is not set, a random password is generated and printed to the backend logs:

```bash
docker compose logs backend | grep "Generated initial admin password"
```

You'll see a line like:

```
Generated initial admin password: aB3x_kL9mN2pQ7wR -- change it immediately
```

Use this to log in at `http://localhost:3000/login`, then create additional users via the admin panel.

To set a specific password instead, add to your `.env`:

```
ADMIN_PASSWORD=your-secure-password-here
```

Password requirements: minimum 10 characters, must contain at least one uppercase letter and one digit.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SECRET_KEY` | **Yes** | — | JWT signing key. App exits if not set. |
| `ADMIN_PASSWORD` | No | (random) | Initial admin password. If unset, generated and logged. |
| `POSTGRES_USER` | No | `crm` | Database username |
| `POSTGRES_PASSWORD` | No | `crm_secret_change_me` | Database password |
| `POSTGRES_DB` | No | `crm` | Database name |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `60` | JWT token lifetime |
| `CORS_ORIGINS` | No | `http://localhost:3000` | Allowed CORS origins |
| `NEXT_PUBLIC_API_URL` | No | `http://localhost:8000` | Backend URL for frontend |
| `SLACK_WEBHOOK_URL` | No | empty | Slack incoming webhook URL for Catalyst managed intake notifications |
| `CRM_FRONTEND_BASE_URL` | No | `http://localhost:3000` | Frontend base URL used in CRM links sent to Slack |

### Gmail Integration (optional)

| Variable | Description |
|----------|-------------|
| `GOOGLE_SERVICE_ACCOUNT_FILE` | Path to service account JSON (mounted at `/app/credentials/`) |
| `GOOGLE_DELEGATED_USER` | Admin email for domain-wide delegation |
| `GMAIL_SYNC_INTERVAL_SECONDS` | Sync interval in seconds (default: 300) |
| `APP_BASE_URL` | Base URL for email tracking links |

To enable Gmail sync:
1. Create a service account in Google Cloud Console
2. Enable the Gmail API
3. Set up domain-wide delegation in Google Workspace Admin
4. Download the service account JSON key to `./backend/credentials/`
5. Set the env vars above in `.env`

### Catalyst managed intake Slack notifications (optional)

Set `SLACK_WEBHOOK_URL` to a Slack incoming webhook URL to notify Slack when a Catalyst managed intake activity is created for a deal. Set `CRM_FRONTEND_BASE_URL` to the public frontend URL so the Slack message links back to the CRM deal.

## Features

- **Contacts** — CRUD, CSV import/export (max 5MB/10k rows), tags, custom fields, ownership tracking
- **Companies** — CRUD with associated contacts and deals
- **Deals** — Pipeline stages: lead, qualified, proposal, negotiation, closed_won, closed_lost
- **Tasks** — Assignable with due dates and status tracking
- **Activities** — Log calls, emails, meetings, notes against contacts/deals
- **Email** — Gmail sync, send, templates, link to contacts/deals
- **Email tracking** — Open tracking (pixel), click tracking (signed URLs), stats
- **Dashboard** — Summary stats, deals by stage, recent activities, upcoming tasks
- **Custom fields** — Admin-defined fields (text, number, date, boolean, select) for contacts/companies
- **Tags** — Flexible labeling for contacts, companies, deals
- **Role-based access** — ADMIN, MANAGER, USER roles with ownership-based data isolation

## Auth

- JWT tokens via HttpOnly secure cookies (SameSite=Lax)
- Login rate-limited to 5 attempts/minute
- Passwords hashed with bcrypt
- Bearer token header also accepted for API clients

## API

All endpoints are under `/api`. Interactive docs at `http://localhost:8000/docs`.

Key routes:

| Route | Description |
|-------|-------------|
| `POST /api/auth/login` | Login (returns cookie) |
| `POST /api/auth/logout` | Logout (clears cookie) |
| `GET /api/auth/me` | Current user |
| `POST /api/auth/users` | Create user (admin) |
| `GET /api/contacts` | List contacts |
| `GET /api/companies` | List companies |
| `GET /api/deals` | List deals |
| `GET /api/tasks` | List tasks |
| `GET /api/activities` | List activities |
| `GET /api/email/messages` | List synced emails |
| `GET /api/dashboard` | Dashboard stats |
| `GET /api/health` | Health check |

## Tech Stack

| Component | Version |
|-----------|---------|
| Python | 3.13 |
| FastAPI | 0.135.1 |
| SQLAlchemy | 2.0.40 (async) |
| PostgreSQL | 17 |
| Node.js | 22 LTS |
| Next.js | 15.3 |
| React | 19 |
| Tailwind CSS | 3.4 |

## Project Structure

```
simple_crm/
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py              # App entrypoint, admin bootstrap
│       ├── config.py            # Settings, env validation
│       ├── auth.py              # JWT, password hashing
│       ├── database.py          # SQLAlchemy async engine
│       ├── models.py            # ORM models
│       ├── schemas.py           # Pydantic schemas
│       ├── gmail_service.py     # Gmail API, tracking
│       ├── gmail_sync_worker.py # Background sync loop
│       └── routes/              # API routers
└── frontend/
    ├── Dockerfile
    ├── package.json
    └── src/
        ├── app/                 # Next.js pages
        ├── components/          # UI components
        └── lib/                 # API client, auth context
```

## Development (without Docker)

**Backend:**

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

export DATABASE_URL="postgresql+asyncpg://crm:crm_secret_change_me@localhost:5432/crm"
export SECRET_KEY="$(openssl rand -hex 32)"

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend:**

```bash
cd frontend
npm ci
npm run dev
```

Runs on `http://localhost:3000`. Requires a PostgreSQL instance and the backend running.

## Security Notes

- `SECRET_KEY` must be set to a strong random value — the app refuses to start otherwise
- Containers run as non-root users
- Database port is not exposed to the host
- Security headers: X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy
- Email HTML is sanitized with DOMPurify before rendering
- CSV imports are sanitized against formula injection
- Email tracking URLs are HMAC-signed to prevent tampering
