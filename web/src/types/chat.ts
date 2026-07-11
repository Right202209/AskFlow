export type ConversationStatus = "active" | "closed" | "transferred";

export interface Conversation {
  id: string;
  user_id: string;
  status: ConversationStatus;
  title: string | null;
  last_message_preview?: string | null;
  created_at: string;
  updated_at: string;
}

/** 回答后证据自检结论（messages.extra.verification / message_end.data.verification）。 */
export interface Verification {
  checked: boolean;
  supported: number;
  total: number;
  invalid_citations: number[];
  verdict: "pass" | "partial" | "fail" | "skipped";
}

/** 回答置信度（messages.extra.answer_confidence）。注意与意图置信度 confidence 是两个概念。 */
export interface AnswerConfidence {
  score: number;
  band: "high" | "medium" | "low";
  retrieval: number;
  verify_pass_rate: number | null;
}

export interface MessageExtra {
  harness_trace?: Record<string, unknown>;
  verification?: Verification | null;
  answer_confidence?: AnswerConfidence | null;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system" | "staff";
  content: string;
  intent: string | null;
  /** 意图置信度（分类器输出）；回答置信度见 answer_confidence。 */
  confidence: number | null;
  sources: { sources: Source[] } | null;
  created_at: string;
  /** REST 历史回放透传的 messages.metadata。 */
  extra?: MessageExtra | null;
  verification?: Verification | null;
  answer_confidence?: AnswerConfidence | null;
  // 用户对该条消息的本地反馈状态。仅前端缓存，后端权威值通过 /feedback 写入。
  feedback?: -1 | 1 | null;
  /** staff_message 帧携带的客服显示名。 */
  staff_name?: string | null;
}

export interface Source {
  /** 与回答中 [n] 标记对齐的引用编号（1 起）。 */
  index?: number;
  doc_id?: string | null;
  chunk_index?: number | null;
  title: string;
  source?: string;
  chunk: string;
  score: number;
}

export type ClientMessageType = "auth" | "message" | "cancel" | "ping";
export type ServerMessageType =
  | "token"
  | "message_end"
  | "error"
  | "intent"
  | "source"
  | "ticket"
  | "handoff"
  | "staff_message"
  | "handoff_update"
  | "pong";

/** 人工接管会话状态（handoff_update 帧的 data.status）。 */
export type HandoffStatus = "queued" | "claimed" | "resolved" | "returned" | "timed_out";

export interface ClientMessage {
  type: ClientMessageType;
  conversation_id?: string;
  content?: string;
  token?: string;
  timestamp: number;
}

export interface ServerMessage {
  type: ServerMessageType;
  conversation_id?: string;
  data?: Record<string, unknown>;
  timestamp?: number;
}
