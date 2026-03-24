export type TicketStatus = "pending" | "processing" | "resolved" | "closed";
export type TicketPriority = "low" | "medium" | "high" | "urgent";

export interface Ticket {
  id: string;
  user_id: string;
  title: string;
  ticket_type: string;
  content: string;
  priority: TicketPriority;
  status: TicketStatus;
  conversation_id: string | null;
  extra: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface CreateTicketRequest {
  title: string;
  ticket_type: string;
  content: string;
  priority: TicketPriority;
  conversation_id?: string;
  extra?: Record<string, unknown>;
}

export interface UpdateTicketRequest {
  status?: TicketStatus;
  priority?: TicketPriority;
}
