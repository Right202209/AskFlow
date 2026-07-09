import { create } from "zustand";
import type { AnalyticsData } from "@/types/admin";
import type { Document } from "@/types/document";
import type { IntentConfig } from "@/types/intent";
import * as adminService from "@/services/admin";
import * as documentService from "@/services/document";

interface AdminState {
  analytics: AnalyticsData | null;
  documents: Document[];
  intents: IntentConfig[];
  isLoading: boolean;
  error: string | null;

  fetchAnalytics: () => Promise<void>;
  fetchDocuments: () => Promise<void>;
  fetchIntents: () => Promise<void>;
}

export const useAdminStore = create<AdminState>()((set) => ({
  analytics: null,
  documents: [],
  intents: [],
  isLoading: false,
  error: null,

  fetchAnalytics: async () => {
    set({ isLoading: true, error: null });
    try {
      const analytics = await adminService.getAnalytics();
      set({ analytics });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "加载数据看板失败" });
    } finally {
      set({ isLoading: false });
    }
  },

  fetchDocuments: async () => {
    set({ isLoading: true, error: null });
    try {
      const documents = await documentService.getDocuments();
      set({ documents });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "加载文档失败" });
    } finally {
      set({ isLoading: false });
    }
  },

  fetchIntents: async () => {
    set({ isLoading: true, error: null });
    try {
      const intents = await adminService.getIntents();
      set({ intents });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "加载意图失败" });
    } finally {
      set({ isLoading: false });
    }
  },
}));
