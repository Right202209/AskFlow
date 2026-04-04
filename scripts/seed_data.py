#!/usr/bin/env python3
"""Seed the database with initial data."""

import asyncio
import sys
import os

from sqlalchemy import inspect, text

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from askflow.core.database import async_session_factory, engine
from askflow.core.security import hash_password
from askflow.models import UserRole


INTENT_SEEDS = [
    {
        "name": "faq",
        "display_name": "FAQ Inquiry",
        "description": "General knowledge questions and FAQ",
        "route_target": "rag",
        "keywords": {"items": ["what", "how", "why", "explain", "tell me"]},
        "examples": {"items": ["What is the return policy?", "How do I reset my password?"]},
        "confidence_threshold": 0.7,
        "priority": 0,
    },
    {
        "name": "product",
        "display_name": "Product Question",
        "description": "Product-related questions and feature inquiries",
        "route_target": "rag",
        "keywords": {"items": ["product", "feature", "support", "compatible"]},
        "examples": {"items": ["Does product X support API Y?", "What features are included?"]},
        "confidence_threshold": 0.7,
        "priority": 1,
    },
    {
        "name": "order_query",
        "display_name": "Order Query",
        "description": "Order status, shipping, and delivery queries",
        "route_target": "tool",
        "keywords": {"items": ["order", "shipping", "delivery", "tracking", "package"]},
        "examples": {"items": ["Where is my order?", "When will my package arrive?"]},
        "confidence_threshold": 0.7,
        "priority": 2,
    },
    {
        "name": "fault_report",
        "display_name": "Fault Report",
        "description": "Bug reports, system errors, fault reports",
        "route_target": "ticket",
        "keywords": {"items": ["error", "bug", "crash", "broken", "not working", "500"]},
        "examples": {"items": ["The login page shows a 500 error", "App crashes on startup"]},
        "confidence_threshold": 0.6,
        "priority": 3,
    },
    {
        "name": "complaint",
        "display_name": "Complaint",
        "description": "Complaints, dissatisfaction, suggestions",
        "route_target": "ticket",
        "keywords": {"items": ["complaint", "terrible", "worst", "disappointed", "unacceptable"]},
        "examples": {"items": ["I want to file a complaint", "The service was terrible"]},
        "confidence_threshold": 0.6,
        "priority": 4,
    },
    {
        "name": "handoff",
        "display_name": "Human Handoff",
        "description": "Requests to talk to a human agent",
        "route_target": "handoff",
        "keywords": {"items": ["human", "agent", "real person", "talk to someone"]},
        "examples": {"items": ["I want to talk to a real person", "Transfer me to an agent"]},
        "confidence_threshold": 0.9,
        "priority": 10,
    },
]


async def seed():
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
        from askflow.repositories.user_repo import UserRepo

        repo = UserRepo(session)

        existing = await repo.get_by_username("admin")
        if not existing:
            await repo.create(
                username="admin",
                email="admin@askflow.local",
                hashed_password=hash_password("admin123"),
                role=UserRole.admin,
            )
            print("Created admin user (admin / admin123)")

        existing = await repo.get_by_username("user1")
        if not existing:
            await repo.create(
                username="user1",
                email="user1@askflow.local",
                hashed_password=hash_password("user123"),
                role=UserRole.user,
            )
            print("Created test user (user1 / user123)")

        from askflow.repositories.intent_config_repo import IntentConfigRepo

        intent_repo = IntentConfigRepo(session)
        for seed in INTENT_SEEDS:
            existing = await intent_repo.get_by_name(seed["name"])
            if not existing:
                await intent_repo.create(**seed)
                print(f"Created intent config: {seed['name']}")

        await session.commit()
    print("Seed complete!")


if __name__ == "__main__":
    asyncio.run(seed())
