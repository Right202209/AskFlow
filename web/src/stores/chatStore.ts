import { create } from "zustand";
import type { Conversation, Message, Source } from "@/types/chat";
import * as chatService from "@/services/chat";

interface ChatState {
  conversations: Conversation[];
  currentConversationId: string | null;
  messages: Record<string, Message[]>;
  streamingTokens: string;
  isStreaming: boolean;
  intent: { label: string; confidence: number } | null;
  sources: Source[];
  isLoadingConversations: boolean;
  isLoadingMessages: boolean;

  fetchConversations: () => Promise<void>;
  selectConversation: (id: string) => Promise<void>;
  createConversation: (title?: string) => Promise<Conversation>;
  appendToken: (token: string) => void;
  finalizeMessage: (conversationId: string) => void;
  setIntent: (intent: { label: string; confidence: number } | null) => void;
  setSources: (sources: Source[]) => void;
  addUserMessage: (conversationId: string, content: string) => void;
  resetStreaming: () => void;
}

export const useChatStore = create<ChatState>()((set, get) => ({
  conversations: [],
  currentConversationId: null,
  messages: {},
  streamingTokens: "",
  isStreaming: false,
  intent: null,
  sources: [],
  isLoadingConversations: false,
  isLoadingMessages: false,

  fetchConversations: async () => {
    set({ isLoadingConversations: true });
    try {
      const conversations = await chatService.getConversations();
      set({ conversations });
    } finally {
      set({ isLoadingConversations: false });
    }
  },

  selectConversation: async (id) => {
    set({ currentConversationId: id, intent: null, sources: [] });
    if (!get().messages[id]) {
      set({ isLoadingMessages: true });
      try {
        const msgs = await chatService.getMessages(id);
        set((state) => ({
          messages: { ...state.messages, [id]: msgs },
        }));
      } finally {
        set({ isLoadingMessages: false });
      }
    }
  },

  createConversation: async (title) => {
    const conv = await chatService.createConversation(title);
    set((state) => ({
      conversations: [conv, ...state.conversations],
      currentConversationId: conv.id,
    }));
    return conv;
  },

  addUserMessage: (conversationId, content) => {
    const msg: Message = {
      id: crypto.randomUUID(),
      conversation_id: conversationId,
      role: "user",
      content,
      intent: null,
      confidence: null,
      sources: null,
      created_at: new Date().toISOString(),
    };
    set((state) => ({
      messages: {
        ...state.messages,
        [conversationId]: [...(state.messages[conversationId] ?? []), msg],
      },
    }));
  },

  appendToken: (token) => {
    set((state) => ({
      streamingTokens: state.streamingTokens + token,
      isStreaming: true,
    }));
  },

  finalizeMessage: (conversationId) => {
    const { streamingTokens, intent, sources } = get();
    if (!streamingTokens) return;
    const msg: Message = {
      id: crypto.randomUUID(),
      conversation_id: conversationId,
      role: "assistant",
      content: streamingTokens,
      intent: intent?.label ?? null,
      confidence: intent?.confidence ?? null,
      sources: sources.length > 0 ? { sources } : null,
      created_at: new Date().toISOString(),
    };
    set((state) => ({
      messages: {
        ...state.messages,
        [conversationId]: [...(state.messages[conversationId] ?? []), msg],
      },
      streamingTokens: "",
      isStreaming: false,
    }));
  },

  setIntent: (intent) => set({ intent }),
  setSources: (sources) => set({ sources }),
  resetStreaming: () => set({ streamingTokens: "", isStreaming: false, intent: null, sources: [] }),
}));
