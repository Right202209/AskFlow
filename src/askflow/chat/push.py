"""跨 worker 的用户推送桥（plan-docs/agent-real-handoff/02 §Design 5，D7）。

客服的 REST 请求可能落在与用户 WS 连接不同的 worker 上。任何 worker 想给某个
用户推帧，都发布到 Redis 频道；每个 worker 的订阅者收到后调本进程的
manager.send_to_user——没持有该用户连接的 worker 天然 no-op，多 worker 正确性
由构造保证，无需连接注册表。模式照抄 agent/service.py 的 route-map 订阅者。
"""

from __future__ import annotations

import asyncio
import json

from askflow.chat.manager import manager
from askflow.chat.protocol import ServerMessage
from askflow.core.logging import get_logger
from askflow.core.redis import redis_client

logger = get_logger(__name__)

CHAT_PUSH_CHANNEL = "askflow:chat:push"

_push_subscriber_task: asyncio.Task | None = None


async def publish_user_push(user_id: str, message: ServerMessage) -> None:
    """向指定用户的所有活跃 WS 连接投递一帧（跨 worker）。Redis 不可用只记日志。"""
    envelope = {"user_id": user_id, "message": message.model_dump(mode="json")}
    try:
        await redis_client.pool.publish(CHAT_PUSH_CHANNEL, json.dumps(envelope))
    except Exception as exc:
        logger.warning("chat_push_publish_failed", user_id=user_id, error=str(exc))


async def _push_listener() -> None:
    try:
        pubsub = redis_client.pool.pubsub()
    except Exception as exc:
        logger.warning("chat_push_subscriber_init_failed", error=str(exc))
        return

    try:
        await pubsub.subscribe(CHAT_PUSH_CHANNEL)
        async for raw in pubsub.listen():
            if not raw or raw.get("type") != "message":
                continue
            await _forward(raw.get("data"))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("chat_push_subscriber_error", error=str(exc))
    finally:
        try:
            await pubsub.unsubscribe(CHAT_PUSH_CHANNEL)
            await pubsub.aclose()
        except Exception:
            pass


async def _forward(data) -> None:
    """单帧转发；坏消息只记日志，绝不让订阅循环退出。"""
    try:
        envelope = json.loads(data)
        message = ServerMessage.model_validate(envelope["message"])
        await manager.send_to_user(str(envelope["user_id"]), message)
    except Exception as exc:
        logger.warning("chat_push_forward_failed", error=str(exc))


def start_chat_push_subscriber() -> asyncio.Task:
    """lifespan 启动期挂上后台订阅协程，已存在则复用。"""
    global _push_subscriber_task
    if _push_subscriber_task and not _push_subscriber_task.done():
        return _push_subscriber_task
    _push_subscriber_task = asyncio.create_task(_push_listener())
    return _push_subscriber_task


async def stop_chat_push_subscriber() -> None:
    global _push_subscriber_task
    task = _push_subscriber_task
    _push_subscriber_task = None
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("chat_push_subscriber_stop_error", error=str(exc))
