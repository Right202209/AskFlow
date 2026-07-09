export interface AnalyticsData {
  total_conversations: number;
  total_messages: number;
  total_tickets: number;
  total_documents: number;
  tickets_by_status: Record<string, number>;
  intent_distribution: Record<string, number>;
  avg_confidence: number;
  // Task 3 新增：替代 avg_confidence 作为可信质量信号的三项指标。
  harness_fallback_rate: number;
  harness_truncate_rate: number;
  thumbs_down_rate_7d: number;
  feedback_total_7d: number;
  // Phase 2 新增：harness 拦截按 reason / flag 维度的分类型计数，
  // 让运营定位"哪一类拦截在涨"。后端可能返回旧版本 schema，所以可选。
  harness_reason_distribution?: Record<string, number>;
  harness_flag_distribution?: Record<string, number>;
}

// Phase 2 项 11:工单系统级看板,后端 /admin/tickets/dashboard 返回结构。
export interface TicketTrendPoint {
  date: string; // YYYY-MM-DD,UTC
  created: number;
  resolved: number;
}

export interface TicketDashboardData {
  open_total: number;
  pending_total: number;
  processing_total: number;
  resolved_total: number;
  closed_total: number;
  sla_breach_total: number;
  sla_hours: number;
  open_by_priority: Record<string, number>;
  oldest_open_age_hours: number | null;
  daily_trend: TicketTrendPoint[];
}
