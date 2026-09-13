import asyncio
from decimal import Decimal
from app.db.session import AsyncSessionLocal
from app.services.auth_service import register_user
from app.services.expense_service import create_expense
from sqlalchemy import select
from app.models.user import User


async def seed():
    async with AsyncSessionLocal() as db:
        print("Checking/seeding demo user...")
        demo_email = "alex@decodelabs.dev"
        stmt = select(User).where(User.email == demo_email)
        res = await db.execute(stmt)
        user = res.scalar_one_or_none()

        if not user:
            user, _ = await register_user(
                db=db,
                email=demo_email,
                password="Password123!",
                full_name="Alex Mercer"
            )
            print(f"Created demo user: {user.email}")

            # Seed 3 expenses matching reference screenshots (Rs.25, Rs.75, Rs.50 -> Rs.150 total)
            await create_expense(
                db=db,
                user_id=user.id,
                amount=Decimal("25.00"),
                description="Domain Registration",
                category="Tools & Software"
            )
            await create_expense(
                db=db,
                user_id=user.id,
                amount=Decimal("75.00"),
                description="Cloud Server",
                category="Infrastructure"
            )
            await create_expense(
                db=db,
                user_id=user.id,
                amount=Decimal("50.00"),
                description="API Gateway",
                category="Infrastructure"
            )
            print("Successfully seeded 3 demo expenses (Rs.150.00 LKR total).")
        else:
            print(f"Demo user {demo_email} already exists.")


if __name__ == "__main__":
    asyncio.run(seed())
