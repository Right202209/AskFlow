import { apiClient } from "./api";
import type { Document } from "@/types/document";

export async function getDocuments(): Promise<Document[]> {
  return apiClient<Document[]>("/api/v1/admin/documents");
}

export async function uploadDocument(formData: FormData): Promise<Document> {
  return apiClient<Document>("/api/v1/embedding/documents", {
    method: "POST",
    body: formData,
  });
}

export async function reindexDocument(id: string): Promise<void> {
  await apiClient<unknown>(`/api/v1/embedding/documents/${id}/reindex`, {
    method: "POST",
  });
}

export async function deleteDocument(id: string): Promise<void> {
  await apiClient<unknown>(`/api/v1/admin/documents/${id}`, {
    method: "DELETE",
  });
}
