export type DocumentStatus = "pending" | "indexing" | "active" | "failed" | "archived";

export interface Document {
  id: string;
  title: string;
  source: string | null;
  file_path: string | null;
  status: DocumentStatus;
  chunk_count: number;
  created_at: string;
  indexed_at: string | null;
  index_error: string | null;
  index_started_at: string | null;
}
