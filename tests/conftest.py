import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from askflow.models.user import User, UserRole


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_user() -> User:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.username = "testuser"
    user.email = "test@test.com"
    user.role = UserRole.user
    user.is_active = True
    return user


@pytest.fixture
def admin_user() -> User:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.username = "admin"
    user.email = "admin@test.com"
    user.role = UserRole.admin
    user.is_active = True
    return user


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.flush = AsyncMock()
    return db
