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
  // 服务端返回的最后一条 assistant 消息 ID，用来给 finalizeMessage 用真实 ID。
  pendingAssistantMessageId: string | null;
  isLoadingConversations: boolean;
  isLoadingMessages: boolean;

  fetchConversations: () => Promise<void>;
  selectConversation: (id: string) => Promise<void>;
  createConversation: (title?: string) => Promise<Conversation>;
  renameConversation: (conversationId: string, title: string | null) => Promise<Conversation>;
  archiveConversation: (conversationId: string) => Promise<Conversation>;
  deleteConversation: (conversationId: string) => Promise<void>;
  appendToken: (token: string) => void;
  finalizeMessage: (conversationId: string) => void;
  setIntent: (intent: { label: string; confidence: number } | null) => void;
  setSources: (sources: Source[]) => void;
  setPendingAssistantMessageId: (id: string | null) => void;
  submitFeedback: (
    conversationId: string,
    messageId: string,
    rating: -1 | 1,
    comment?: string,
  ) => Promise<void>;
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
  pendingAssistantMessageId: null,
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

  renameConversation: async (conversationId, title) => {
    const conversation = await chatService.renameConversation(conversationId, title);
    set((state) => ({
      conversations: state.conversations.map((item) =>
        item.id === conversationId ? conversation : item,
      ),
    }));
    return conversation;
  },

  archiveConversation: async (conversationId) => {
    const conversation = await chatService.archiveConversation(conversationId);
    set((state) => ({
      conversations: state.conversations.map((item) =>
        item.id === conversationId ? conversation : item,
      ),
    }));
    return conversation;
  },

  deleteConversation: async (conversationId) => {
    await chatService.deleteConversation(conversationId);
    set((state) => {
      const nextMessages = { ...state.messages };
      delete nextMessages[conversationId];

      return {
        conversations: state.conversations.filter((item) => item.id !== conversationId),
        messages: nextMessages,
        currentConversationId:
          state.currentConversationId === conversationId ? null : state.currentConversationId,
      };
    });
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
    const { streamingTokens, intent, sources, pendingAssistantMessageId } = get();
    if (!streamingTokens) return;
    const msg: Message = {
      // 优先用服务端落库的 ID，否则前端临时 UUID（仅在 message_end 缺帧时兜底）。
      id: pendingAssistantMessageId ?? crypto.randomUUID(),
      conversation_id: conversationId,
      role: "assistant",
      content: streamingTokens,
      intent: intent?.label ?? null,
      confidence: intent?.confidence ?? null,
      sources: sources.length > 0 ? { sources } : null,
      created_at: new Date().toISOString(),
      feedback: null,
    };
    set((state) => ({
      messages: {
        ...state.messages,
        [conversationId]: [...(state.messages[conversationId] ?? []), msg],
      },
      streamingTokens: "",
      isStreaming: false,
      pendingAssistantMessageId: null,
    }));
  },

  setIntent: (intent) => set({ intent }),
  setSources: (sources) => set({ sources }),
  setPendingAssistantMessageId: (id) => set({ pendingAssistantMessageId: id }),

  submitFeedback: async (conversationId, messageId, rating, comment) => {
    // 乐观更新：先标本地状态，失败回滚 + 抛错给上层弹 toast。
    const previous = get().messages[conversationId] ?? [];
    set((state) => ({
      messages: {
        ...state.messages,
        [conversationId]: previous.map((m) =>
          m.id === messageId ? { ...m, feedback: rating } : m,
        ),
      },
    }));
    try {
      await chatService.submitFeedback(messageId, rating, comment);
    } catch (err) {
      set((state) => ({
        messages: { ...state.messages, [conversationId]: previous },
      }));
      throw err;
    }
  },

  resetStreaming: () =>
    set({
      streamingTokens: "",
      isStreaming: false,
      intent: null,
      sources: [],
      pendingAssistantMessageId: null,
    }),
}));
