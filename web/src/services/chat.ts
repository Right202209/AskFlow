import { apiClient } from "./api";
import type { Conversation, Message } from "@/types/chat";

export async function getConversations(
  limit = 20,
  offset = 0,
): Promise<Conversation[]> {
  return apiClient<Conversation[]>(
    `/api/v1/chat/conversations?limit=${limit}&offset=${offset}`,
  );
}

export async function createConversation(
  title?: string,
): Promise<Conversation> {
  return apiClient<Conversation>("/api/v1/chat/conversations", {
    method: "POST",
    body: JSON.stringify({ title: title ?? null }),
  });
}

export async function getMessages(
  conversationId: string,
): Promise<Message[]> {
  return apiClient<Message[]>(
    `/api/v1/chat/conversations/${conversationId}/messages`,
  );
}

export async function renameConversation(
  conversationId: string,
  title: string | null,
): Promise<Conversation> {
  return apiClient<Conversation>(`/api/v1/chat/conversations/${conversationId}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
}

export async function archiveConversation(
  conversationId: string,
): Promise<Conversation> {
  return apiClient<Conversation>(`/api/v1/chat/conversations/${conversationId}/archive`, {
    method: "POST",
  });
}

export async function deleteConversation(
  conversationId: string,
): Promise<{ deleted: boolean }> {
  return apiClient<{ deleted: boolean }>(`/api/v1/chat/conversations/${conversationId}`, {
    method: "DELETE",
  });
}
