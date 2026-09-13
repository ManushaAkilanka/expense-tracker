# Expense Tracker

A production-ready, multi-tenant personal finance tracker built with FastAPI, SQLAlchemy 2.0 (async), Jinja2 server-side rendering, and Tailwind CSS.

---

## Architecture

```
Internet / Clients
       ↓
Reverse Proxy / HTTPS (Nginx / Caddy / Cloudflare)
  [SSL Termination • Rate Limiting • Security Buffering]
       ↓ HTTP (Reverse Proxy Header Forwarding)
Uvicorn / Application Worker(s)
       ↓ ASGI
FastAPI Application
  [Argon2id Auth • Session & CSRF Middleware • Business Logic • Jinja2 SSR]
       ↓ Async SQLAlchemy 2.0 (asyncpg / aiosqlite)
Database (PostgreSQL in Production • SQLite in Local Dev)
```

---

## Table of Contents

1. [Local Development](#local-development)
   - [Prerequisites](#prerequisites)
   - [Virtual Environment Setup](#virtual-environment-setup)
   - [Dependency Installation](#dependency-installation)
   - [Environment Setup](#environment-setup)
   - [Database Migrations](#database-migrations)
   - [Starting Development Server](#starting-development-server)
   - [Running Automated Tests](#running-automated-tests)
   - [Seeding Demo Data (Optional)](#seeding-demo-data-optional)
2. [Production Handoff Guide](#production-handoff-guide)
   - [Production Architecture & Prerequisites](#production-architecture--prerequisites)
   - [Required Environment Variables](#required-environment-variables)
   - [Generating a Strong SECRET_KEY](#generating-a-strong-secret_key)
   - [Database Production Configuration (PostgreSQL)](#database-production-configuration-postgresql)
   - [Database Migration & Rollback Procedure](#database-migration--rollback-procedure)
   - [Production Startup Command](#production-startup-command)
   - [Reverse Proxy & HTTPS Configuration](#reverse-proxy--https-configuration)
   - [Host Validation (ALLOWED_HOSTS)](#host-validation-allowed_hosts)
   - [Google OAuth Cloud Console Setup](#google-oauth-cloud-console-setup)
   - [Session Revocation Architectural Limitation](#session-revocation-architectural-limitation)
   - [Rate Limiting Guidance](#rate-limiting-guidance)
   - [Backups, Monitoring & Operations](#backups-monitoring--operations)
3. [Production Readiness & Responsibility Matrix](#production-readiness--responsibility-matrix)

---

## Local Development

### Prerequisites
- **Python**: 3.11 or higher (developed and tested on Python 3.13)
- **Git**: installed and configured
- **SQLite3**: standard library (no external service required)

### Virtual Environment Setup
```bash
# 1. Clone the repository
git clone <repo-url>
cd Finance_Tracker

# 2. Create virtual environment
python -m venv .venv

# 3. Activate virtual environment
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Windows CMD:
.\.venv\Scripts\activate.bat
# macOS / Linux:
source .venv/bin/activate
```

### Dependency Installation
```bash
pip install -r requirements.txt
```

### Environment Setup
```bash
# Copy example configuration template
cp .env.example .env
```
The default `.env` configuration works out of the box for local development using SQLite (`./expense_tracker.db` or `./finance_tracker.db`).

### Database Migrations
Apply Alembic migrations to create the schema:
```bash
alembic upgrade head
```
Check migration status:
```bash
alembic current
```

### Starting Development Server
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
Open your browser at:
👉 **`http://127.0.0.1:8000`**

### Running Automated Tests
```bash
pytest -v
```
All 67 tests across authentication, expense validation, multi-tenant isolation, adversarial security, and production configuration should pass.

### Seeding Demo Data (Optional)
To populate a local test account with sample transactions:
```bash
python seed.py
```
> [!WARNING]
> `seed.py` creates a demo account (`alex@example.com` / `Password123!`) with preset data.
> **Never run `seed.py` in a production environment.**

---

## Production Handoff Guide

### Production Architecture & Prerequisites
In production, the application is designed to operate behind an HTTPS-terminating reverse proxy (such as Nginx, Caddy, or AWS ALB) connected to a PostgreSQL database:

- **Host OS**: Linux (Ubuntu 22.04 / 24.04 LTS recommended)
- **Runtime**: Python 3.11+
- **Reverse Proxy**: Nginx or Caddy with TLS (Let's Encrypt / Certbot)
- **Database**: PostgreSQL 14+ with `asyncpg` support

---

### Required Environment Variables

Configure the following variables in the production environment (e.g. systemd service file, Docker environment, or secrets manager):

| Variable | Type | Production Value | Description |
|:---|:---:|:---|:---|
| `ENVIRONMENT` | `str` | `production` | **Required.** Activates production safety checks and strict guards. |
| `DEBUG` | `bool` | `False` | **Required.** Disables `/docs` OpenAPI UI and detailed error disclosures. |
| `SECRET_KEY` | `str` | *`<strong 64-char hex>`* | **Required.** Cryptographic secret for signing sessions and CSRF tokens. Application aborts startup if left at default. |
| `DATABASE_URL` | `str` | `postgresql+asyncpg://user:pass@host:5432/dbname` | **Required.** PostgreSQL async connection string. |
| `SECURE_COOKIE` | `bool` | `True` | **Required.** Marks session cookies `Secure` (transmitted only over HTTPS). |
| `HSTS_ENABLED` | `bool` | `True` | **Required.** Injects `Strict-Transport-Security` header once HTTPS is validated. |
| `ALLOWED_HOSTS` | `str` | `yourdomain.com,www.yourdomain.com` | **Required.** Whitelist of allowed Host headers (blocks Host header poisoning). |
| `SESSION_COOKIE_NAME` | `str` | `expense_session` | Name of the session cookie. |
| `SESSION_MAX_AGE` | `int` | `86400` | Session lifetime in seconds (24 hours). |
| `GOOGLE_CLIENT_ID` | `str` | *`<client-id>`* | Optional. OAuth Client ID from Google Cloud Console. |
| `GOOGLE_CLIENT_SECRET` | `str` | *`<client-secret>`* | Optional. OAuth Client Secret from Google Cloud Console. |
| `GOOGLE_REDIRECT_URI` | `str` | `https://yourdomain.com/auth/google/callback` | OAuth redirect callback. **Must use HTTPS in production.** |

---

### Generating a Strong SECRET_KEY
Run this command in the terminal to generate a 256-bit cryptographically random key:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
Set the output as `SECRET_KEY` in your production environment.

> [!CAUTION]
> The application includes a hard startup guard: if `ENVIRONMENT=production` and `SECRET_KEY` is empty or equal to the development placeholder, FastAPI will raise a fatal `RuntimeError` and terminate immediately.

---

### Database Production Configuration (PostgreSQL)

1. Provision a PostgreSQL database and create a dedicated application user:
   ```sql
   CREATE DATABASE finance_tracker;
   CREATE USER tracker_user WITH ENCRYPTED PASSWORD 'your_secure_password';
   GRANT ALL PRIVILEGES ON DATABASE finance_tracker TO tracker_user;
   ```
2. Configure `DATABASE_URL` in your production environment:
   ```ini
   DATABASE_URL="postgresql+asyncpg://tracker_user:your_secure_password@db.internal:5432/finance_tracker"
   ```
3. The application automatically detects `postgresql+asyncpg://` and switches to the production async connection engine without SQLite-specific thread arguments.

---

### Database Migration & Rollback Procedure

#### Applying Migrations (Deployment)
Before starting or restarting application workers during deployment:
```bash
alembic upgrade head
```
Verify the current schema revision:
```bash
alembic current
```

#### Rollback Procedure (Disaster Recovery)
If a release must be rolled back:
```bash
# Roll back one migration:
alembic downgrade -1

# Or roll back to a specific revision ID:
alembic downgrade <revision_id>
```

---

### Production Startup Command

Run the application using Uvicorn with standard production flags:
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 4 --proxy-headers --forwarded-allow-ips='*'
```

#### Systemd Service Example (`/etc/systemd/system/financetracker.service`):
```ini
[Unit]
Description=Expense Tracker
After=network.target postgresql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/finance_tracker
EnvironmentFile=/etc/finance_tracker/.env
ExecStart=/var/www/finance_tracker/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 4 --proxy-headers --forwarded-allow-ips='127.0.0.1'
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

---

### Reverse Proxy & HTTPS Configuration

The application must be deployed behind an HTTPS-terminating reverse proxy.

#### Nginx Configuration Example:
```nginx
# Rate limiting zone for auth endpoints
limit_req_zone $binary_remote_addr zone=auth_limit:10m rate=5r/m;
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=60r/m;

server {
    listen 80;
    server_name expenses.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name expenses.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/expenses.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/expenses.yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Static file caching
    location /static/ {
        alias /var/www/finance_tracker/app/static/;
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }

    # Authentication rate limiting
    location ~ ^/(sign-in|sign-up|auth/) {
        limit_req zone=auth_limit burst=10 nodelay;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # General traffic
    location / {
        limit_req zone=api_limit burst=30 nodelay;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

### Host Validation (ALLOWED_HOSTS)
When `ALLOWED_HOSTS` is defined (e.g. `ALLOWED_HOSTS="expenses.yourdomain.com,www.expenses.yourdomain.com"`), `TrustedHostMiddleware` is automatically engaged. Requests with mismatched or spoofed `Host` headers are rejected with HTTP 400.
In local development, leaving `ALLOWED_HOSTS=""` permits `localhost` and `127.0.0.1` without restriction.

---

### Google OAuth Cloud Console Setup

To enable Google OAuth in production, complete the following steps in the [Google Cloud Console](https://console.cloud.google.com/):

1. **Create or Select Project**: Open Google Cloud Console and select your organization project.
2. **OAuth Consent Screen**:
   - User Type: **External**
   - App Name: `Expense Tracker`
   - User support email & Developer contact info: your operational contact email
   - Scopes: `openid`, `email`, `profile`
3. **Create Credentials**:
   - Go to **APIs & Services > Credentials**
   - Click **Create Credentials > OAuth Client ID**
   - Application Type: **Web application**
   - Name: `Expense Tracker Web Client`
   - **Authorized JavaScript origins**:
     `https://expenses.yourdomain.com`
   - **Authorized redirect URIs**:
     `https://expenses.yourdomain.com/auth/google/callback`
4. **Deploy Credentials**:
   - Copy the Client ID into `GOOGLE_CLIENT_ID`
   - Copy the Client Secret into `GOOGLE_CLIENT_SECRET`
   - Set `GOOGLE_REDIRECT_URI=https://expenses.yourdomain.com/auth/google/callback`

> [!NOTE]
> If Google OAuth credentials are not provided, the application automatically disables the Google button and provides clean email/password authentication with zero errors.

---

### Session Revocation Architectural Limitation

> [!IMPORTANT]
> **Process-Local Revocation Store**:
> In Phase 12, logout replay protection was implemented using an in-memory revoked session registry (`_REVOKED_SESSIONS` in `app/core/session.py`).
> - For single-process deployments (`--workers 1`), this provides full replay protection.
> - For multi-worker deployments (`--workers > 1`), a session revoked on Worker A is stored in Worker A's memory. If a client replays the revoked cookie against Worker B, Worker B will not be aware of the revocation until session expiration (`SESSION_MAX_AGE=86400`).
> 
> **Production Recommendation**: When deploying across multiple application workers or multi-node clusters, replace `_REVOKED_SESSIONS` with a shared backend store such as Redis.

---

### Rate Limiting Guidance

> [!IMPORTANT]
> **Application-Level Rate Limiting Is Not Implemented**:
> The FastAPI application does not contain in-process rate limiting dependencies.
> Rate limiting for `/sign-in`, `/sign-up`, and sensitive mutation routes must be enforced at the **infrastructure / reverse proxy level** (e.g. Nginx `limit_req`, Caddy `rate_limit`, Cloudflare WAF, or AWS WAF).

---

### Backups, Monitoring & Operations

#### 1. PostgreSQL Backups & Retention
- **Automated Daily Dumps**: Configure a scheduled cron job or managed cloud backup (e.g., AWS RDS automated backups):
  ```bash
  pg_dump -Fc -h db.internal -U tracker_user finance_tracker > /backups/finance_tracker_$(date +%Y%m%d_%H%M%S).dump
  ```
- **Retention Policy**: Retain daily backups for 30 days, weekly backups for 12 weeks, and monthly backups for 1 year.
- **Restore Testing**: Periodically perform dry-run restores into an isolated staging database to verify backup integrity:
  ```bash
  pg_restore -d finance_tracker_test /backups/test_restore.dump
  ```

#### 2. Health Checks & Monitoring
- **Health Endpoint**: The application exposes `/health`:
  - Returns `200 OK` with `{"status": "healthy", "database": "connected"}` when operational.
  - If the database is unreachable, returns `{"status": "degraded", "database": "unavailable"}` without exposing internal exception strings.
- Configure external uptime monitors (UptimeRobot, Datadog, Prometheus Blackbox) to poll `https://expenses.yourdomain.com/health` every 60 seconds.

#### 3. Log Aggregation & Alerting
- Structured log format is output to `stdout`/`stderr` using ISO timestamps:
  `YYYY-MM-DDTHH:MM:SS  LEVEL  logger_name  message`
- Ingest logs via `systemd-journald`, Vector, or Promtail/Loki.
- Alert on spikes in HTTP 500 status codes or repeated health check degradation.

---

## Production Readiness & Responsibility Matrix

| Checklist Item | Status | Layer | Notes |
|:---|:---:|:---:|:---|
| **Argon2id Password Hashing** | ✅ CONFIGURED | Application | Memory-hard password protection |
| **CSRF Protection** | ✅ CONFIGURED | Application | Cryptographic token required on all POSTs |
| **Signed Session Cookies** | ✅ CONFIGURED | Application | `itsdangerous` HMAC-SHA256 cookie signing |
| **Session Fixation Guard** | ✅ CONFIGURED | Application | Session ID rotated on authentication |
| **Multi-Tenant DB Isolation** | ✅ CONFIGURED | Application | All queries scoped strictly to `user_id` |
| **Open Redirect Defense** | ✅ CONFIGURED | Application | `safe_redirect_target` prevents external redirects |
| **SQL Injection Defense** | ✅ CONFIGURED | Application | SQLAlchemy 2.0 async parameterized queries |
| **XSS Defense** | ✅ CONFIGURED | Application | Jinja2 autoescaping + custom sanitization |
| **CSV Formula Injection Defense** | ✅ CONFIGURED | Application | Prefixes formula triggers (`=,+,-,@`) with `'` |
| **Security Headers** | ✅ CONFIGURED | Application | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy` |
| **Production Key Guard** | ✅ CONFIGURED | Application | Startup aborted if default `SECRET_KEY` in production |
| **Alembic Schema & Head Revision** | ✅ CONFIGURED | Application | Migration `ad5ae0c9eb8b` at head |
| **PostgreSQL Driver Support** | ✅ CONFIGURED | Application | `asyncpg` installed; dialect autodetection |
| **Currency Uniformity** | ✅ CONFIGURED | Application | Unified to `Rs.` and `LKR` across all views |
| **Environment Configuration** | 📋 REQUIRES DEPLOYMENT | Infrastructure | Set `ENVIRONMENT=production`, strong `SECRET_KEY`, `DEBUG=False` |
| **PostgreSQL Server Provisioning** | 📋 REQUIRES DEPLOYMENT | Infrastructure | Managed PostgreSQL cluster required |
| **Domain DNS & SSL/TLS** | 📋 REQUIRES DEPLOYMENT | Infrastructure | Domain DNS records + Let's Encrypt certificates |
| **Reverse Proxy (Nginx/Caddy)** | 📋 REQUIRES DEPLOYMENT | Infrastructure | Reverse proxy with TLS termination |
| **Authentication Rate Limiting** | 📋 REQUIRES DEPLOYMENT | Infrastructure | Nginx `limit_req` or WAF rate limiting |
| **Multi-Worker Shared Sessions** | 📋 REQUIRES DEPLOYMENT | Future/Infra | Redis integration recommended if `--workers > 1` |
| **Automated Backups & Retention** | 📋 REQUIRES DEPLOYMENT | Infrastructure | Scheduled `pg_dump` and periodic restore validation |
| **Log Monitoring & Alerting** | 📋 REQUIRES DEPLOYMENT | Infrastructure | Monitoring `/health` and aggregating journald logs |
| **Google Cloud Console OAuth Setup** | 📋 REQUIRES DEPLOYMENT | Developer | Authorized origin & callback URL registration |
