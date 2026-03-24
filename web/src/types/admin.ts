export interface AnalyticsData {
  total_conversations: number;
  total_messages: number;
  total_tickets: number;
  total_documents: number;
  tickets_by_status: Record<string, number>;
  intent_distribution: Record<string, number>;
  avg_confidence: number;
}
