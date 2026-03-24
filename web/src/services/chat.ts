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
