import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db.session import get_db

router = APIRouter(tags=["Health"])
logger = logging.getLogger(__name__)


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """Lightweight health check confirming database connectivity.

    Returns a safe status message. Database error details are logged
    server-side only and never exposed to the caller.
    """
    db_ok = True
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        # Log the real error internally; never expose connection strings or
        # filesystem paths to the HTTP response.
        logger.exception("Health check: database connectivity failure")
        db_ok = False

    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "unavailable",
        "service": "Expense Tracker",
        "version": "3.12.0",
    }
