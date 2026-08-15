"""FrigoCore — one-off bootstrap: create the first administrator account.

Run once, after the auth migration is applied, via:
    docker exec -it frigocore-backend python scripts/create_admin.py
"""
import asyncio
import getpass
import sys

sys.path.insert(0, ".")

from sqlalchemy import select  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.database import async_session_factory  # noqa: E402
from app.enums import UserRole  # noqa: E402
from app.models.user import User  # noqa: E402


async def main() -> None:
    username = input("Username: ").strip()
    email = input("Email: ").strip()
    full_name = input("Full name: ").strip()
    password = getpass.getpass("Password (min 8 chars): ")
    if len(password) < 8:
        print("Password must be at least 8 characters.")
        return

    async with async_session_factory() as session:
        existing = await session.scalar(select(User).where(User.username == username))
        if existing:
            print(f"User '{username}' already exists — aborting.")
            return
        user = User(
            username=username,
            email=email,
            full_name=full_name,
            hashed_password=hash_password(password),
            role=UserRole.ADMIN,
        )
        session.add(user)
        await session.commit()
        print(f"Created admin '{username}'.")


if __name__ == "__main__":
    asyncio.run(main())
