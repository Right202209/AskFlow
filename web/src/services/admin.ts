import { apiClient } from "./api";
import type { AnalyticsData, TicketDashboardData } from "@/types/admin";
import type { IntentConfig, CreateIntentRequest, UpdateIntentRequest } from "@/types/intent";
import type { Ticket, TicketStatus } from "@/types/ticket";

export async function getAnalytics(): Promise<AnalyticsData> {
  return apiClient<AnalyticsData>("/api/v1/admin/analytics");
}

export async function getTicketDashboard(): Promise<TicketDashboardData> {
  return apiClient<TicketDashboardData>("/api/v1/admin/tickets/dashboard");
}

export async function getIntents(): Promise<IntentConfig[]> {
  return apiClient<IntentConfig[]>("/api/v1/admin/intents");
}

export async function createIntent(data: CreateIntentRequest): Promise<IntentConfig> {
  return apiClient<IntentConfig>("/api/v1/admin/intents", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateIntent(
  id: string,
  data: UpdateIntentRequest,
): Promise<IntentConfig> {
  return apiClient<IntentConfig>(`/api/v1/admin/intents/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deleteIntent(id: string): Promise<void> {
  await apiClient(`/api/v1/admin/intents/${id}`, { method: "DELETE" });
}

export async function getAdminTickets(
  limit = 50,
  offset = 0,
  status?: TicketStatus,
): Promise<Ticket[]> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });

  if (status) {
    params.set("status", status);
  }

  return apiClient<Ticket[]>(`/api/v1/admin/tickets?${params.toString()}`);
}
