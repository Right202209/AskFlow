// knowledge-loop 01：知识缺口雷达（/admin/gaps）的前端类型。

export type GapStatus = "open" | "promoted" | "dismissed";

export interface KnowledgeGap {
  id: string;
  question: string;
  question_norm: string;
  status: GapStatus;
  frequency: number;
  // 每类失败信号的计数，如 {"clarify": 2, "negative_feedback": 1}。
  signals: Record<string, number>;
  last_intent: string | null;
  example_conversation_id: string | null;
  example_message_id: string | null;
  promoted_doc_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface RelatedGap {
  id: string;
  question: string;
  frequency: number;
  similarity: number;
}

// knowledge-loop 02：草稿知识条目（/admin/knowledge）。
export type DraftStatus = "draft" | "approved" | "rejected";

export interface KnowledgeDraft {
  id: string;
  gap_id: string | null;
  question: string;
  answer: string;
  status: DraftStatus;
  source_ticket_id: string | null;
  source_conversation_id: string | null;
  synthesis: { model?: string; prompt_version?: string; generated?: boolean } | null;
  created_by: string | null;
  reviewed_by: string | null;
  published_doc_id: string | null;
  review_note: string | null;
  created_at: string;
  updated_at: string;
}

export interface DraftCreateRequest {
  ticket_id?: string;
  conversation_id?: string;
  manual_answer?: string;
  synthesize?: boolean;
}
