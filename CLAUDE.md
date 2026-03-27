# Simple CRM

Full-stack CRM platform for managing contacts, companies, deals, tasks, and email.

## Stack

- **Frontend:** Next.js 15, React 19, TypeScript, shadcn/ui (Radix), Tailwind CSS 3
- **Backend:** FastAPI, SQLAlchemy (async), Postgres 17, bcrypt + JWT auth
- **Containerization:** Docker Compose

## Ports

| Service | Host | Container |
|---------|------|-----------|
| Frontend | 3000 | 3000 |
| Backend | 8000 | 8000 |
| Database | internal | 5432 |

## Directory Structure

```
backend/app/
├── routes/        # FastAPI route handlers (auth, contacts, companies, deals, tasks, activities, email, dashboard, search, notifications, api_keys, custom_fields, tags)
├── models.py      # All SQLAlchemy models + enums
├── schemas.py     # All Pydantic request/response schemas
├── auth.py        # JWT + API key auth, password hashing, role-based access
├── config.py      # Pydantic settings from env
├── database.py    # Async engine + session factory
└── main.py        # App factory, middleware, router registration

frontend/src/
├── app/           # Next.js pages (dashboard, contacts, companies, deals, tasks, email, admin, login)
├── components/    # app-shell, sidebar, search-modal, timeline, notifications, ui/ (shadcn primitives)
└── lib/           # api.ts (fetch helpers), auth.tsx (context + hooks), utils.ts (cn)
```

## Key Commands

```bash
# Start
docker compose up -d

# Rebuild
docker compose up -d --build

# Backend logs
docker compose logs -f backend

# Frontend dev (outside Docker)
cd frontend && npm run dev

# Backend shell
docker compose exec backend bash
```

## Coding Standards

### Backend
- Routes in `backend/app/routes/` — one file per domain
- Models in `models.py`, schemas in `schemas.py` (both single files)
- Auth: `get_current_user` dependency, `require_role(UserRole.ADMIN)` for admin routes
- Pagination: `page`/`per_page` query params, return `PaginatedResponse`
- Search: `.ilike(f"%{search}%")` with OR conditions
- Updates: `data.model_dump(exclude_unset=True)` + `setattr()` loop
- Register new routers in `main.py`

### Frontend
- `"use client"` on interactive pages, wrap in `<AppShell>`
- API calls via `apiFetch<T>(path, options)` from `lib/api.ts`
- Forms in Radix `<Dialog>`, tables in `<Card>` wrappers
- State: `useState` + `useCallback` + `useEffect` for data loading
- Icons: lucide-react, styling: Tailwind + `cn()` utility

## Deployment

Deployed to LXD VM `simple-crm-prod` on lxd01 (10.46.0.8).
- Domain: https://simple-crm.deltaops.tech
- VM IP: 192.168.3.157, Nebula: 10.46.0.30
- Reverse proxy: Nginx Proxy Manager -> port 3000
- API calls proxied through Next.js rewrites (`/api/*` -> `http://backend:8000/api/*`)

## Environment

See `.env.example`. Key vars: `DATABASE_URL`, `SECRET_KEY`, `CORS_ORIGINS`, `NEXT_PUBLIC_API_URL` (empty for deployed environments).
