export type ConversationStatus = "active" | "closed" | "transferred";

export interface Conversation {
  id: string;
  user_id: string;
  status: ConversationStatus;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  intent: string | null;
  confidence: number | null;
  sources: { sources: Source[] } | null;
  created_at: string;
  // 用户对该条消息的本地反馈状态。仅前端缓存，后端权威值通过 /feedback 写入。
  feedback?: -1 | 1 | null;
}

export interface Source {
  title: string;
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
  | "pong";

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
