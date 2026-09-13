import html
import logging
import logging.config
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.core.session import SessionMiddleware
from app.db.session import async_engine, Base
import app.db.base  # Ensure all models are registered with Base.metadata
from app.routes import (
    health_router,
    auth_router,
    dashboard_router,
    expenses_router,
    transactions_router,
)

# ── Logging configuration ────────────────────────────────────────────────────
# Structured, level-appropriate logging. Passwords/tokens must never be logged.
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="app/templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Auto-create tables for seamless local development.
    # In production, tables are managed by Alembic migrations (alembic upgrade head).
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info(
        "Expense Tracker started | env=%s debug=%s",
        settings.ENVIRONMENT,
        settings.DEBUG,
    )
    yield
    # Graceful shutdown
    await async_engine.dispose()
    logger.info("Expense Tracker shutdown complete.")


app = FastAPI(
    title=settings.APP_NAME,
    version="3.12.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url=None,
    lifespan=lifespan,
)

# Attach Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    # HSTS — only injected when explicitly enabled (behind HTTPS in production)
    if settings.HSTS_ENABLED:
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains"
        )
    return response

# Attach Session & CSRF Middleware
app.add_middleware(SessionMiddleware)

# Attach Trusted Host Middleware if ALLOWED_HOSTS is configured (production)
if settings.allowed_hosts_list:
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts_list)

# Mount Static Files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Register Routers
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(expenses_router)
app.include_router(transactions_router)


# Global Exception Handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code in (status.HTTP_303_SEE_OTHER, status.HTTP_302_FOUND, status.HTTP_307_TEMPORARY_REDIRECT):
        location = exc.headers.get("Location") if exc.headers else "/sign-in"
        return RedirectResponse(url=location, status_code=exc.status_code)
    if exc.status_code == 404:
        return await not_found_handler(request, exc)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    raw_detail = getattr(exc, 'detail', 'The requested resource could not be found.')
    escaped_detail = html.escape(str(raw_detail))
    if "text/html" in request.headers.get("accept", ""):
        return HTMLResponse(
            f"""<!DOCTYPE html>
            <html>
            <head><title>404 Not Found - {settings.APP_NAME}</title>
            <script src="https://cdn.tailwindcss.com"></script></head>
            <body class="bg-slate-50 flex items-center justify-center min-h-screen font-sans">
              <div class="text-center p-8 max-w-md bg-white rounded-2xl border border-slate-200 shadow-sm">
                <div class="text-5xl font-black text-indigo-600 mb-2">404</div>
                <h1 class="text-xl font-bold text-slate-800 mb-2">Record or Page Not Found</h1>
                <p class="text-sm text-slate-500 mb-6">{escaped_detail}</p>
                <a href="/dashboard" class="inline-block px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-xl shadow-sm transition">Back to Dashboard</a>
              </div>
            </body>
            </html>""",
            status_code=404
        )
    return JSONResponse(status_code=404, content={"detail": str(raw_detail)})


@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})

