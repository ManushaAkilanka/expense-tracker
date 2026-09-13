from app.routes.health import router as health_router
from app.routes.auth import router as auth_router
from app.routes.dashboard import router as dashboard_router
from app.routes.expenses import router as expenses_router
from app.routes.transactions import router as transactions_router

__all__ = [
    "health_router",
    "auth_router",
    "dashboard_router",
    "expenses_router",
    "transactions_router",
]
