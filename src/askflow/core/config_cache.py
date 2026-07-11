"""通用运行时配置缓存：本地 TTL + 失效 epoch + Redis pub/sub 失效广播。

从 agent/service.py 的 route_map 缓存原样抽取（plan-docs/ops-platform/01 D1）：
- TTL 兜底：即便 pub/sub 漏消息，`ttl_seconds` 后也能最终一致；
- epoch 守卫：`get()` 打 DB 前先记录失效序号，加载完成后序号变了就拒绝写回缓存——
  防止"订阅者刚清掉的缓存被一个在途加载的旧快照覆盖回去"的竞态；
- publish 失败直接吞（Redis 不可用时 TTL 是兜底），订阅协程由 lifespan 启停。

loader 自己负责异常处理（失败返回空值），本类不吞 loader 异常。
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar

from askflow.core.logging import get_logger
from askflow.core.redis import redis_client

logger = get_logger(__name__)

# 本地缓存 TTL：与原 ROUTE_MAP_CACHE_TTL_SECONDS 一致。
CONFIG_CACHE_TTL_SECONDS = 60.0
_INVALIDATE_MESSAGE = "invalidate"

T = TypeVar("T")


class ConfigCache(Generic[T]):
    """单值配置缓存；每类配置（路由表、提示词表…）各建一个实例、各占一个频道。"""

    def __init__(
        self,
        *,
        name: str,
        channel: str,
        loader: Callable[[], Awaitable[T]],
        ttl_seconds: float = CONFIG_CACHE_TTL_SECONDS,
    ) -> None:
        self._name = name
        self._channel = channel
        self._loader = loader
        self._ttl = ttl_seconds
        self._value: T | None = None
        self._loaded_at: float = 0.0
        self._invalidate_seq: int = 0
        self._subscriber_task: asyncio.Task | None = None

    @property
    def snapshot(self) -> T | None:
        """当前缓存值（可能为 None）；仅供测试与诊断只读。"""
        return self._value

    @property
    def invalidate_seq(self) -> int:
        return self._invalidate_seq

    async def get(self) -> T:
        """TTL 命中直接返回；否则 epoch 守卫下重新加载。"""
        now = time.monotonic()
        if self._value is not None and now - self._loaded_at < self._ttl:
            return self._value

        # 打 DB 之前先记录失效序号——加载完再比一次，期间 invalidate 触发就跳过缓存写入。
        pre_load_seq = self._invalidate_seq
        value = await self._loader()
        if self._invalidate_seq == pre_load_seq:
            self._value = value
            self._loaded_at = now
        else:
            # 这一份快照可能已不是最新；让下一次 get() 重新加载，避免覆盖回旧状态。
            logger.info("config_cache_load_skipped_concurrent_invalidate", cache=self._name)
        return value

    def invalidate(self) -> None:
        """清本地缓存并递增 epoch——下一次 get() 必然重新加载。"""
        self._value = None
        self._loaded_at = 0.0
        self._invalidate_seq += 1

    async def publish_invalidation(self) -> None:
        """通知其他 worker 也清缓存。Redis 不可用直接吞——TTL 兜底。"""
        try:
            await redis_client.pool.publish(self._channel, _INVALIDATE_MESSAGE)
        except Exception as e:
            logger.warning("config_cache_publish_failed", cache=self._name, error=str(e))

    async def _listener(self) -> None:
        try:
            pubsub = redis_client.pool.pubsub()
        except Exception as e:
            logger.warning("config_cache_subscriber_init_failed", cache=self._name, error=str(e))
            return

        try:
            await pubsub.subscribe(self._channel)
            async for message in pubsub.listen():
                if not message or message.get("type") != "message":
                    continue
                self.invalidate()
                logger.info("config_cache_invalidated_via_pubsub", cache=self._name)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("config_cache_subscriber_error", cache=self._name, error=str(e))
        finally:
            try:
                await pubsub.unsubscribe(self._channel)
                await pubsub.aclose()
            except Exception:
                pass

    def start_subscriber(self) -> asyncio.Task:
        """lifespan 启动期挂上后台订阅协程，已存在则复用。"""
        if self._subscriber_task and not self._subscriber_task.done():
            return self._subscriber_task
        self._subscriber_task = asyncio.create_task(self._listener())
        return self._subscriber_task

    async def stop_subscriber(self) -> None:
        """lifespan 关停期取消后台订阅协程，避免悬挂连接。"""
        task = self._subscriber_task
        self._subscriber_task = None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning("config_cache_subscriber_stop_error", cache=self._name, error=str(e))
