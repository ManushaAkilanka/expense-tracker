from decimal import Decimal
import json
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.expense_service import create_expense
from tests.conftest import AuthenticatedSessionClient


@pytest.mark.asyncio
async def test_transactions_page_and_search(
    db_session: AsyncSession,
    user_a: User,
    auth_client_a: AuthenticatedSessionClient,
):
    await create_expense(db_session, user_id=user_a.id, amount=Decimal("25.00"), description="Domain Registration", category="Tools")
    await create_expense(db_session, user_id=user_a.id, amount=Decimal("75.00"), description="Cloud Server", category="Infrastructure")
    await create_expense(db_session, user_id=user_a.id, amount=Decimal("50.00"), description="API Gateway", category="Infrastructure")

    # 1. Access transactions page
    res = await auth_client_a.get("/transactions")
    assert res.status_code == 200
    assert "Transaction History / Audit" in res.text
    assert "Domain Registration" in res.text
    assert "Cloud Server" in res.text
    assert "API Gateway" in res.text

    # 2. Search query filter
    res_search = await auth_client_a.get("/transactions?q=Gateway")
    assert res_search.status_code == 200
    assert "API Gateway" in res_search.text


@pytest.mark.asyncio
async def test_csv_and_json_export(
    db_session: AsyncSession,
    user_a: User,
    auth_client_a: AuthenticatedSessionClient,
):
    # CSV Export
    csv_res = await auth_client_a.get("/transactions/export/csv")
    assert csv_res.status_code == 200
    assert csv_res.headers["content-type"] == "text/csv; charset=utf-8"
    assert "Sequence,Transaction ID,Timestamp (UTC)" in csv_res.text

    # JSON Export
    json_res = await auth_client_a.get("/transactions/export/json")
    assert json_res.status_code == 200
    assert json_res.headers["content-type"] == "application/json"
    data = json_res.json()
    assert "transactions" in data
    assert "count" in data
    assert data["count"] >= 3
