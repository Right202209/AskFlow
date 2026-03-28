export type TicketStatus = "pending" | "processing" | "resolved" | "closed";
export type TicketPriority = "low" | "medium" | "high" | "urgent";

export interface Ticket {
  id: string;
  user_id: string;
  title: string;
  type: string;
  description: string | null;
  assignee: string | null;
  content: Record<string, unknown> | null;
  priority: TicketPriority;
  status: TicketStatus;
  conversation_id: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface CreateTicketRequest {
  title: string;
  type: string;
  description?: string;
  priority: TicketPriority;
  conversation_id?: string;
  content?: Record<string, unknown>;
}

export interface UpdateTicketRequest {
  status?: TicketStatus;
  assignee?: string;
  priority?: TicketPriority;
  content?: Record<string, unknown>;
}
