import { apiClient } from "./api";
import type { Ticket, CreateTicketRequest, UpdateTicketRequest } from "@/types/ticket";

export async function getTickets(
  limit = 20,
  offset = 0,
): Promise<Ticket[]> {
  return apiClient<Ticket[]>(
    `/api/v1/tickets?limit=${limit}&offset=${offset}`,
  );
}

export async function getTicket(id: string): Promise<Ticket> {
  return apiClient<Ticket>(`/api/v1/tickets/${id}`);
}

export async function createTicket(data: CreateTicketRequest): Promise<Ticket> {
  return apiClient<Ticket>("/api/v1/tickets", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateTicket(
  id: string,
  data: UpdateTicketRequest,
): Promise<Ticket> {
  return apiClient<Ticket>(`/api/v1/tickets/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}
