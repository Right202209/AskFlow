#!/usr/bin/env python3
"""Create a new user."""

import asyncio
import sys
import os
import argparse

from sqlalchemy import inspect, text

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from askflow.core.database import async_session_factory, engine
from askflow.core.security import hash_password
from askflow.models import UserRole
from askflow.repositories.user_repo import UserRepo


async def create_user(username: str, email: str, password: str, role: str):
    async with engine.connect() as conn:
        has_alembic_version = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).has_table("alembic_version")
        )
        if not has_alembic_version:
            raise RuntimeError("Database is not initialized. Run 'make migrate' first.")

        version = (
            await conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
        ).scalar_one_or_none()
        if version is None:
            raise RuntimeError(
                "Database schema exists but is not tracked by Alembic. Run 'alembic stamp head' or recreate the database."
            )

    async with async_session_factory() as session:
        repo = UserRepo(session)
        existing = await repo.get_by_username(username)
        if existing:
            print(f"User '{username}' already exists")
            return

        await repo.create(
            username=username,
            email=email,
            hashed_password=hash_password(password),
            role=UserRole(role),
        )
        await session.commit()
        print(f"Created user: {username} ({role})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a new user")
    parser.add_argument("--username", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--role", default="user", choices=["user", "agent", "admin"])
    args = parser.parse_args()
    asyncio.run(create_user(args.username, args.email, args.password, args.role))
