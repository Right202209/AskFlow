// ops-platform 01：提示词模板契约，与 schemas/prompt.py 对齐。

export interface PromptTemplate {
  id: string;
  key: string;
  description: string | null;
  variables: string[];
  is_active: boolean;
  active_version: number | null;
  content: string | null;
  updated_at: string;
}

export interface PromptVersion {
  id: string;
  version: number;
  content: string;
  comment: string | null;
  created_by: string | null;
  created_at: string;
}

export interface PromptUpdateRequest {
  content: string;
  comment?: string | null;
}
