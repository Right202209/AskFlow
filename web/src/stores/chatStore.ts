import { create } from "zustand";
import type {
  AnswerConfidence,
  Conversation,
  ConversationStatus,
  HandoffStatus,
  Message,
  Source,
  Verification,
} from "@/types/chat";
import * as chatService from "@/services/chat";

/** handoff 状态 → 会话状态的本地投影，保持列表/网关提示与服务端一致。 */
const HANDOFF_TO_CONVERSATION_STATUS: Record<HandoffStatus, ConversationStatus> = {
  queued: "transferred",
  claimed: "transferred",
  resolved: "active",
  returned: "active",
  timed_out: "active",
};

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
  // message_end 帧携带的自检结论与回答置信度，finalizeMessage 时并入消息。
  pendingVerification: Verification | null;
  pendingAnswerConfidence: AnswerConfidence | null;
  // 当前会话的人工接管状态（handoff / handoff_update 帧驱动）。
  handoffStatus: HandoffStatus | null;
  handoffTicketId: string | null;
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
  setPendingVerification: (verification: Verification | null) => void;
  setPendingAnswerConfidence: (confidence: AnswerConfidence | null) => void;
  setHandoffStatus: (
    conversationId: string,
    status: HandoffStatus | null,
    ticketId?: string | null,
  ) => void;
  addStaffMessage: (conversationId: string, content: string, staffName: string | null) => void;
  submitFeedback: (
    conversationId: string,
    messageId: string,
    rating: -1 | 1,
    comment?: string,
  ) => Promise<void>;
  addUserMessage: (conversationId: string, content: string) => void;
  resetStreaming: () => void;
}

/** REST 历史回放：把 extra 里的自检/置信度提到消息顶层，与 WS 实时路径同构。 */
function normalizeHistoryMessage(message: Message): Message {
  return {
    ...message,
    verification: message.verification ?? message.extra?.verification ?? null,
    answer_confidence: message.answer_confidence ?? message.extra?.answer_confidence ?? null,
  };
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
  pendingVerification: null,
  pendingAnswerConfidence: null,
  handoffStatus: null,
  handoffTicketId: null,
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
    set({
      currentConversationId: id,
      intent: null,
      sources: [],
      handoffStatus: null,
      handoffTicketId: null,
    });
    if (!get().messages[id]) {
      set({ isLoadingMessages: true });
      try {
        const msgs = await chatService.getMessages(id);
        set((state) => ({
          messages: { ...state.messages, [id]: msgs.map(normalizeHistoryMessage) },
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
    const {
      streamingTokens,
      intent,
      sources,
      pendingAssistantMessageId,
      pendingVerification,
      pendingAnswerConfidence,
    } = get();
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
      verification: pendingVerification,
      answer_confidence: pendingAnswerConfidence,
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
      pendingVerification: null,
      pendingAnswerConfidence: null,
    }));
  },

  setIntent: (intent) => set({ intent }),
  setSources: (sources) => set({ sources }),
  setPendingAssistantMessageId: (id) => set({ pendingAssistantMessageId: id }),
  setPendingVerification: (verification) => set({ pendingVerification: verification }),
  setPendingAnswerConfidence: (confidence) => set({ pendingAnswerConfidence: confidence }),

  setHandoffStatus: (conversationId, status, ticketId = null) => {
    set((state) => {
      // 会话列表状态同步更新（任意会话），横幅状态只跟当前会话走。
      const projected = status ? HANDOFF_TO_CONVERSATION_STATUS[status] : null;
      const conversations = projected
        ? state.conversations.map((item) =>
            item.id === conversationId ? { ...item, status: projected } : item,
          )
        : state.conversations;
      if (state.currentConversationId !== conversationId) {
        return { conversations };
      }
      return { conversations, handoffStatus: status, handoffTicketId: ticketId };
    });
  },

  addStaffMessage: (conversationId, content, staffName) => {
    set((state) => {
      const existing = state.messages[conversationId];
      // 未加载过消息缓存的会话不追加：交给 selectConversation 的历史拉取兜底，
      // 否则半空缓存会挡掉后续整段历史加载。
      if (!existing) return state;
      const msg: Message = {
        id: crypto.randomUUID(),
        conversation_id: conversationId,
        role: "staff",
        content,
        intent: null,
        confidence: null,
        sources: null,
        created_at: new Date().toISOString(),
        staff_name: staffName,
      };
      return { messages: { ...state.messages, [conversationId]: [...existing, msg] } };
    });
  },

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
      pendingVerification: null,
      pendingAnswerConfidence: null,
      handoffStatus: null,
      handoffTicketId: null,
    }),
}));
