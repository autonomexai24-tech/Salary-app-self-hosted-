# Salary & Advance Tracker

Production-ready payroll and attendance app with a React frontend and FastAPI backend.

## Stack

- React, Vite, TypeScript, Tailwind, shadcn/ui
- FastAPI, SQLAlchemy, PostgreSQL
- Nginx reverse proxy for the production container

## Local Development

Install frontend dependencies:

```bash
npm ci
```

Create backend environment variables:

```bash
cp backend/.env.example backend/.env
```

Run the backend:

```bash
python -m pip install -r requirements.txt
python -m backend.init_db
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Run the frontend:

```bash
npm run dev
```

The Vite dev app uses same-origin API paths by default and proxies `/api` plus `/uploads` to `http://127.0.0.1:8000`. Override the browser API target with `VITE_API_BASE_URL` only when the frontend is served from a different host.

## Easypanel Deployment

Deploy this repository from GitHub using the root `Dockerfile`.

The container:

- builds the React app with `npm ci && npm run build`
- installs backend dependencies from `backend/requirements.txt`
- initializes the database schema on startup
- runs FastAPI on `127.0.0.1:8000`
- serves the frontend through Nginx on port `80`
- proxies API routes from the same public domain to FastAPI

Set these environment variables in Easypanel:

```bash
APP_ENV=production
DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@HOST:5432/DB_NAME
JWT_SECRET_KEY=<random-long-secret-at-least-32-characters>
CORS_ORIGINS=https://your-app-domain.example
FRONTEND_URL=https://your-app-domain.example
APP_BASE_URL=https://your-app-domain.example
UPLOAD_PATH=/app/backend/uploads
UPLOAD_URL_PATH=/uploads
BOOTSTRAP_ADMIN_EMAIL=admin@dhanushpackaging.com
BOOTSTRAP_ADMIN_NAME=Dhanush Packaging Admin
BOOTSTRAP_ADMIN_PASSWORD=<set-a-strong-unique-admin-password>
SEED_DEMO_DATA=false
```

Optional environment variables:

```bash
APP_NAME=Payroll OS Backend
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
DB_POOL_RECYCLE_SECONDS=1800
DB_POOL_TIMEOUT_SECONDS=30
DB_STARTUP_RETRIES=30
DB_STARTUP_RETRY_SECONDS=2
ACCESS_TOKEN_EXPIRE_MINUTES=60
PASSWORD_BCRYPT_ROUNDS=12
MAX_LOGO_UPLOAD_BYTES=2097152
```

For persistent company logos, locked payslip PDFs, and payslip ZIP exports, mount a read-write volume at:

```bash
/app/backend/uploads
```

This path must match `UPLOAD_PATH`. The app validates the directory and creates the `logos/` and `payslips/` subdirectories during startup.

## First Admin User

The production startup creates the first admin only when the `users` table is empty and
`BOOTSTRAP_ADMIN_PASSWORD` is set to a strong production value. The local default
password is intentionally blocked in production.

Use this login after the first successful deployment:

```text
User ID / Email: admin@dhanushpackaging.com
Password: the value you set for BOOTSTRAP_ADMIN_PASSWORD in Easypanel
```

If the database already exists and you need to create or reset the admin from the
Easypanel app shell, run:

```bash
python -m backend.admin_cli \
  --email admin@dhanushpackaging.com \
  --full-name "Dhanush Packaging Admin" \
  --password "set-a-strong-unique-admin-password"
```

If the `users` table is empty, you can also create the initial admin once through
the bootstrap API:

```bash
curl -X POST https://your-app-domain.example/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@dhanushpackaging.com","full_name":"Dhanush Packaging Admin","password":"set-a-strong-unique-admin-password"}'
```

Then sign in through the web UI with that email and password.
