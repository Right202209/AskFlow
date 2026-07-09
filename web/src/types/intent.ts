export interface IntentConfig {
  id: string;
  name: string;
  display_name: string;
  description: string | null;
  route_target: string;
  keywords: Record<string, unknown> | null;
  examples: Record<string, unknown> | null;
  confidence_threshold: number;
  is_active: boolean;
  priority: number;
  created_at: string;
  updated_at: string;
}

export interface CreateIntentRequest {
  name: string;
  display_name: string;
  description?: string;
  route_target: string;
  keywords?: Record<string, unknown>;
  examples?: Record<string, unknown>;
  confidence_threshold?: number;
  is_active?: boolean;
  priority?: number;
}

export interface UpdateIntentRequest {
  display_name?: string;
  description?: string;
  route_target?: string;
  keywords?: Record<string, unknown>;
  examples?: Record<string, unknown>;
  confidence_threshold?: number;
  is_active?: boolean;
  priority?: number;
}
