from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.core.database import get_db
from askflow.core.auth import get_current_user
from askflow.models.user import User

# 统一的依赖别名可以让路由函数签名更简洁。
DBSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
