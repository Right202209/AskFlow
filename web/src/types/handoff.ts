// agent-real-handoff 02：人工接管收件箱（/admin/handoffs）的前端类型。
import type { Message } from "@/types/chat";

export type HandoffSessionStatus =
  | "queued"
  | "claimed"
  | "resolved"
  | "returned"
  | "timed_out";

export interface HandoffPayload {
  recent_messages?: Array<{ role: string; content: string; created_at: string | null }>;
  intent_history?: string[];
  user_meta?: { user_id?: string; session_start_at?: string | null };
  ticket_refs?: string[];
  flags?: string[];
}

export interface HandoffSession {
  id: string;
  conversation_id: string;
  status: HandoffSessionStatus;
  summary: string;
  payload: HandoffPayload;
  assignee: string | null;
  created_at: string;
  claimed_at: string | null;
  closed_at: string | null;
}

export interface HandoffDetail {
  session: HandoffSession;
  messages: Message[];
}
