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
}
