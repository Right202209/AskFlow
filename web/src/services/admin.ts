import { apiClient } from "./api";
import type { AnalyticsData } from "@/types/admin";
import type { IntentConfig, CreateIntentRequest, UpdateIntentRequest } from "@/types/intent";

export async function getAnalytics(): Promise<AnalyticsData> {
  return apiClient<AnalyticsData>("/api/v1/admin/analytics");
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
