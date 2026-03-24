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

  fetchAnalytics: () => Promise<void>;
  fetchDocuments: () => Promise<void>;
  fetchIntents: () => Promise<void>;
}

export const useAdminStore = create<AdminState>()((set) => ({
  analytics: null,
  documents: [],
  intents: [],
  isLoading: false,

  fetchAnalytics: async () => {
    set({ isLoading: true });
    try {
      const analytics = await adminService.getAnalytics();
      set({ analytics });
    } finally {
      set({ isLoading: false });
    }
  },

  fetchDocuments: async () => {
    set({ isLoading: true });
    try {
      const documents = await documentService.getDocuments();
      set({ documents });
    } finally {
      set({ isLoading: false });
    }
  },

  fetchIntents: async () => {
    set({ isLoading: true });
    try {
      const intents = await adminService.getIntents();
      set({ intents });
    } finally {
      set({ isLoading: false });
    }
  },
}));
