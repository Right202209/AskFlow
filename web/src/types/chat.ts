export interface Conversation {
  id: string;
  user_id: string;
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
}

export interface Source {
  title: string;
  chunk: string;
  score: number;
}

export type ClientMessageType = "message" | "cancel" | "ping";
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
  timestamp: number;
}

export interface ServerMessage {
  type: ServerMessageType;
  conversation_id?: string;
  data?: Record<string, unknown>;
  timestamp?: number;
}
