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

The Vite dev app uses `http://localhost:8000` as its default API URL. Override it with `VITE_API_BASE_URL` if needed.

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
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DB_NAME
JWT_SECRET_KEY=<random-long-secret-at-least-32-characters>
ALLOWED_ORIGINS=https://your-app-domain.example
UPLOAD_DIR=/app/backend/uploads
UPLOAD_URL_PATH=/uploads
```

Optional environment variables:

```bash
APP_NAME=Payroll OS Backend
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
ACCESS_TOKEN_EXPIRE_MINUTES=60
PASSWORD_BCRYPT_ROUNDS=12
MAX_LOGO_UPLOAD_BYTES=2097152
```

For persistent company logos, mount a volume at:

```bash
/app/backend/uploads
```

## First Admin User

After deployment, create the initial admin user once:

```bash
curl -X POST https://your-app-domain.example/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","full_name":"Admin User","password":"replace-with-a-strong-password"}'
```

Then sign in through the web UI with that email and password.
