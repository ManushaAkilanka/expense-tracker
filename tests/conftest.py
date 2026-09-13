import os
import tempfile
from typing import AsyncGenerator
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.main import app
from app.db.session import Base, get_db
from app.core.security import sign_session_data, generate_csrf_token
from app.models.user import User
from app.services.auth_service import register_user

TEST_DB_PATH = os.path.join(tempfile.gettempdir(), "test_expense_tracker.db")
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    future=True
)
TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


@pytest.fixture(scope="session", autouse=True)
async def setup_test_database():
    """Create all tables before test run and clean up after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except OSError:
            pass


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def user_a(db_session: AsyncSession) -> User:
    user, _ = await register_user(
        db_session,
        email="user_a@decodelabs.dev",
        password="Password123!",
        full_name="User Alpha"
    )
    if not user:
        from sqlalchemy import select
        stmt = select(User).where(User.email == "user_a@decodelabs.dev")
        res = await db_session.execute(stmt)
        user = res.scalar_one()
    return user


@pytest.fixture
async def user_b(db_session: AsyncSession) -> User:
    user, _ = await register_user(
        db_session,
        email="user_b@decodelabs.dev",
        password="Password123!",
        full_name="User Beta"
    )
    if not user:
        from sqlalchemy import select
        stmt = select(User).where(User.email == "user_b@decodelabs.dev")
        res = await db_session.execute(stmt)
        user = res.scalar_one()
    return user


class AuthenticatedSessionClient:
    def __init__(self, user: User, base_client: AsyncClient):
        self.user = user
        self.client = base_client
        self.session_id = f"sess-{user.id[:8]}"
        self.csrf_token = generate_csrf_token(self.session_id)
        session_payload = {
            "user_id": user.id,
            "user_email": user.email,
            "user_name": user.full_name,
            "session_id": self.session_id
        }
        self.cookie_val = sign_session_data(session_payload)
        self.client.cookies.set("expense_session", self.cookie_val)

    async def get(self, url: str, **kwargs):
        return await self.client.get(url, **kwargs)

    async def post(self, url: str, data: dict = None, **kwargs):
        payload = data.copy() if data else {}
        if "_csrf_token" not in payload:
            payload["_csrf_token"] = self.csrf_token
        return await self.client.post(url, data=payload, **kwargs)


@pytest.fixture
async def auth_client_a(user_a: User) -> AsyncGenerator[AuthenticatedSessionClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield AuthenticatedSessionClient(user_a, ac)


@pytest.fixture
async def auth_client_b(user_b: User) -> AsyncGenerator[AuthenticatedSessionClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield AuthenticatedSessionClient(user_b, ac)
