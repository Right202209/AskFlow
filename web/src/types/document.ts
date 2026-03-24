export type DocumentStatus = "pending" | "processing" | "indexed" | "failed";

export interface Document {
  id: string;
  title: string;
  source: string | null;
  filename: string;
  status: DocumentStatus;
  chunk_count: number;
  created_at: string;
  indexed_at: string | null;
}
