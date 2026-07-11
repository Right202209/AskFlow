import { apiClient } from "./api";
import type { AnalyticsData, SystemHealthData, TicketDashboardData } from "@/types/admin";
import type { Document } from "@/types/document";
import type { HandoffDetail, HandoffSession, HandoffSessionStatus } from "@/types/handoff";
import type { IntentConfig, CreateIntentRequest, UpdateIntentRequest } from "@/types/intent";
import type { PromptTemplate, PromptVersion, PromptUpdateRequest } from "@/types/prompt";
import type {
  DraftCreateRequest,
  DraftStatus,
  GapStatus,
  KnowledgeDraft,
  KnowledgeGap,
  RelatedGap,
} from "@/types/knowledge";
import type { Ticket, TicketStatus } from "@/types/ticket";

export async function getAnalytics(): Promise<AnalyticsData> {
  return apiClient<AnalyticsData>("/api/v1/admin/analytics");
}

export async function getTicketDashboard(): Promise<TicketDashboardData> {
  return apiClient<TicketDashboardData>("/api/v1/admin/tickets/dashboard");
}

export async function getSystemHealth(): Promise<SystemHealthData> {
  return apiClient<SystemHealthData>("/api/v1/admin/system/health");
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

// knowledge-loop 01：知识缺口雷达。与 getAdminTickets 同构，apiClient 只取 data 数组。
export async function getKnowledgeGaps(
  status: GapStatus = "open",
  limit = 20,
  offset = 0,
): Promise<KnowledgeGap[]> {
  const params = new URLSearchParams({
    status,
    limit: String(limit),
    offset: String(offset),
  });
  return apiClient<KnowledgeGap[]>(`/api/v1/admin/gaps?${params.toString()}`);
}

export async function dismissKnowledgeGap(id: string): Promise<KnowledgeGap> {
  return apiClient<KnowledgeGap>(`/api/v1/admin/gaps/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ status: "dismissed" }),
  });
}

export async function getRelatedGaps(id: string): Promise<RelatedGap[]> {
  return apiClient<RelatedGap[]>(`/api/v1/admin/gaps/${id}/related`);
}

// knowledge-loop 02：草稿知识条目评审流。
export async function createDraftFromGap(
  gapId: string,
  body: DraftCreateRequest,
): Promise<KnowledgeDraft> {
  return apiClient<KnowledgeDraft>(`/api/v1/admin/gaps/${gapId}/draft`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function getKnowledgeDrafts(
  status: DraftStatus = "draft",
  limit = 20,
  offset = 0,
): Promise<KnowledgeDraft[]> {
  const params = new URLSearchParams({
    status,
    limit: String(limit),
    offset: String(offset),
  });
  return apiClient<KnowledgeDraft[]>(`/api/v1/admin/drafts?${params.toString()}`);
}

export async function updateKnowledgeDraft(
  id: string,
  body: { question?: string; answer?: string },
): Promise<KnowledgeDraft> {
  return apiClient<KnowledgeDraft>(`/api/v1/admin/drafts/${id}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export async function approveKnowledgeDraft(id: string): Promise<Document> {
  return apiClient<Document>(`/api/v1/admin/drafts/${id}/approve`, { method: "POST" });
}

export async function rejectKnowledgeDraft(
  id: string,
  reviewNote?: string,
): Promise<KnowledgeDraft> {
  return apiClient<KnowledgeDraft>(`/api/v1/admin/drafts/${id}/reject`, {
    method: "POST",
    body: JSON.stringify({ review_note: reviewNote ?? null }),
  });
}

// agent-real-handoff 02：人工接管收件箱。
export async function getHandoffs(
  status: HandoffSessionStatus = "queued",
  limit = 20,
  offset = 0,
): Promise<HandoffSession[]> {
  const params = new URLSearchParams({
    status,
    limit: String(limit),
    offset: String(offset),
  });
  return apiClient<HandoffSession[]>(`/api/v1/admin/handoffs?${params.toString()}`);
}

export async function getHandoffDetail(id: string): Promise<HandoffDetail> {
  return apiClient<HandoffDetail>(`/api/v1/admin/handoffs/${id}`);
}

export async function claimHandoff(id: string): Promise<HandoffSession> {
  return apiClient<HandoffSession>(`/api/v1/admin/handoffs/${id}/claim`, { method: "POST" });
}

export async function replyHandoff(id: string, content: string): Promise<HandoffSession> {
  return apiClient<HandoffSession>(`/api/v1/admin/handoffs/${id}/reply`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export async function resolveHandoff(
  id: string,
  status: "resolved" | "returned",
  closeConversation = false,
): Promise<HandoffSession> {
  return apiClient<HandoffSession>(`/api/v1/admin/handoffs/${id}/resolve`, {
    method: "POST",
    body: JSON.stringify({ status, close_conversation: closeConversation }),
  });
}

// ops-platform 01：提示词模板管理。列表/版本历史 apiClient 只取 data；PaginatedResponse 也如此。
export async function getPrompts(): Promise<PromptTemplate[]> {
  return apiClient<PromptTemplate[]>("/api/v1/admin/prompts");
}

export async function getPromptVersions(
  key: string,
  limit = 50,
  offset = 0,
): Promise<PromptVersion[]> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return apiClient<PromptVersion[]>(
    `/api/v1/admin/prompts/${encodeURIComponent(key)}/versions?${params.toString()}`,
  );
}

export async function updatePrompt(
  key: string,
  body: PromptUpdateRequest,
): Promise<PromptTemplate> {
  return apiClient<PromptTemplate>(`/api/v1/admin/prompts/${encodeURIComponent(key)}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export async function activatePromptVersion(
  key: string,
  versionNumber: number,
): Promise<PromptTemplate> {
  return apiClient<PromptTemplate>(
    `/api/v1/admin/prompts/${encodeURIComponent(key)}/activate/${versionNumber}`,
    { method: "POST" },
  );
}
