from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AnalyticsResponse(BaseModel):
    total_conversations: int = 0
    total_messages: int = 0
    total_tickets: int = 0
    total_documents: int = 0
    tickets_by_status: dict[str, int] = {}
    intent_distribution: dict[str, int] = {}
    avg_confidence: float = 0.0
    # 新质量信号：harness 兜底比例、截断比例、7 天 thumbs-down 占比。
    # 替换空洞的 avg_confidence 作为"线上是不是变差了"的判定依据。
    harness_fallback_rate: float = 0.0
    harness_truncate_rate: float = 0.0
    thumbs_down_rate_7d: float = 0.0
    feedback_total_7d: int = 0
    # 分类型拦截计数：按 harness_trace.reason 与 flags[*] 聚合，
    # 让运营能直接看到"哪一类拦截最频繁"——例如 prompt_control_request 突增
    # 通常预示注入扫描，response_truncated 突增预示 max_response_chars 偏紧。
    harness_reason_distribution: dict[str, int] = {}
    harness_flag_distribution: dict[str, int] = {}


class TicketTrendPoint(BaseModel):
    """一天的工单进出量,用于折线/柱状对比。"""

    date: str  # YYYY-MM-DD,UTC
    created: int = 0
    resolved: int = 0


class TicketDashboardResponse(BaseModel):
    """Admin 工单系统级看板:全局排队、SLA 超时、优先级分布、7 天趋势。"""

    # 排队总数(pending + processing),决定看板顶部"待跟进"卡片。
    open_total: int = 0
    pending_total: int = 0
    processing_total: int = 0
    resolved_total: int = 0
    closed_total: int = 0
    # SLA 超时:pending/processing 中 created_at 超过 settings.ticket_sla_hours 的条数。
    sla_breach_total: int = 0
    sla_hours: int = 24
    # 按优先级拆开 open 工单,运营能定位"high/urgent 是不是堆积"。
    open_by_priority: dict[str, int] = {}
    # 未处理工单中最老的 age(小时);None 表示当前无未处理工单。
    oldest_open_age_hours: float | None = None
    # 最近 7 天每日创建 vs 已解决,反映吞吐与积压趋势。
    daily_trend: list[TicketTrendPoint] = []


class SystemHealthResponse(BaseModel):
    """Admin "System" 面板：依赖探活 + 文档积压 + 索引新鲜度 + 24h 审计 + 版本。"""

    # 依赖整体状态与逐项结果——status=ok|degraded，checks[dep]=ok|error:<ClassName>。
    status: str = "ok"
    checks: dict[str, str] = {}
    # 文档按状态计数（含 Slice 03 的 pending/indexing/failed 积压）+ 最老 pending 年龄。
    documents_by_status: dict[str, int] = {}
    oldest_pending_age_hours: float | None = None
    # 索引新鲜度：active 文档分块总数 + 最近一次 indexed_at。
    chunks_total: int = 0
    last_indexed_at: datetime | None = None
    # 最近 24h 审计事件按 action 计数（Slice 02 审计表）。
    audit_events_24h: dict[str, int] = {}
    # 线上跑的 harness 策略版本与应用版本——确认部署一致性。
    harness_policy_version: str = ""
    app_version: str = ""
