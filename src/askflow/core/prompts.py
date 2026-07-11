"""提示词读路径（ops-platform/01）：DB 模板优先，代码常量兜底。

`prompt_cache` 与 route_map 共用 ConfigCache 机制（TTL 60s + epoch + pub/sub）。
**兜底规则**：DB 行缺失 / 未激活 / DB 不可用时回落到代码默认常量并记
`prompt_fallback_default`——系统绝不因提示词表为空而无法作答。

默认常量保留在原模块（prompt_builder / intent_classifier / nodes）原名不动：
`NO_RESULTS_REFUSAL` 等被 gap_recorder、eval harness 按"共享常量"契约引用，
改名收益为零、破坏面大；本模块用懒导入避免 core → rag/agent 的环。
"""

from __future__ import annotations

from askflow.core.config_cache import ConfigCache
from askflow.core.logging import get_logger

logger = get_logger(__name__)

PROMPT_INVALIDATE_CHANNEL = "askflow:prompts:invalidate"
# 单个模板内容上限——超过按 422 拒绝（比任何理智的提示词都大）。
MAX_PROMPT_CONTENT_CHARS = 20_000
# 版本历史分页页大小。
MAX_VERSIONS_LISTED = 50

# 稳定业务键；新增模板键必须同时补 _default_prompt 的兜底映射。
PROMPT_KEY_RAG_SYSTEM = "rag.system"
PROMPT_KEY_RAG_CONTEXT = "rag.context"
PROMPT_KEY_RAG_NO_RESULTS = "rag.fallback_no_results"
PROMPT_KEY_RAG_LLM_DOWN = "rag.fallback_llm_down"
PROMPT_KEY_INTENT_CLASSIFIER = "intent.classifier"
PROMPT_KEY_AGENT_CLARIFY = "agent.clarify"


async def _load_prompts() -> dict[str, str]:
    """key → 生效内容；失败返回空表（全部走代码兜底）。"""
    try:
        # 函数内导入：与 route_map loader 同理，便于单测打桩且避免启动期连 DB。
        from askflow.core.database import async_session_factory
        from askflow.repositories.prompt_repo import PromptRepo

        async with async_session_factory() as db:
            return await PromptRepo(db).load_active_contents()
    except Exception as e:
        logger.warning("failed_to_load_prompts", error=str(e))
        return {}


prompt_cache: ConfigCache[dict[str, str]] = ConfigCache(
    name="prompts",
    channel=PROMPT_INVALIDATE_CHANNEL,
    loader=_load_prompts,
)


async def get_prompt(key: str) -> str:
    """按键取当前生效提示词；DB 缺行时回落代码默认并告警。"""
    prompts = await prompt_cache.get()
    content = prompts.get(key)
    if content:
        return content
    logger.warning("prompt_fallback_default", key=key)
    return _default_prompt(key)


def _default_prompt(key: str) -> str:
    """代码默认常量映射（懒导入切断 core → rag/agent 的环）。"""
    from askflow.agent.intent_classifier import INTENT_PROMPT
    from askflow.agent.nodes import CLARIFY_RESPONSE
    from askflow.rag.prompt_builder import (
        CONTEXT_TEMPLATE,
        LLM_DOWN_FALLBACK_PREFIX,
        NO_RESULTS_REFUSAL,
        SYSTEM_PROMPT,
    )

    defaults = {
        PROMPT_KEY_RAG_SYSTEM: SYSTEM_PROMPT,
        PROMPT_KEY_RAG_CONTEXT: CONTEXT_TEMPLATE,
        PROMPT_KEY_RAG_NO_RESULTS: NO_RESULTS_REFUSAL,
        PROMPT_KEY_RAG_LLM_DOWN: LLM_DOWN_FALLBACK_PREFIX,
        PROMPT_KEY_INTENT_CLASSIFIER: INTENT_PROMPT,
        PROMPT_KEY_AGENT_CLARIFY: CLARIFY_RESPONSE,
    }
    if key not in defaults:
        raise KeyError(f"Unknown prompt key: {key}")
    return defaults[key]
