import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { ChatComposer } from "@/components/chat/ChatComposer";
import { ChatInfoPanel } from "@/components/chat/ChatInfoPanel";
import { ConversationList } from "@/components/chat/ConversationList";
import { CreateTicketDialog } from "@/components/chat/CreateTicketDialog";
import { MessageList } from "@/components/chat/MessageList";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useChatStore } from "@/stores/chatStore";
import type { Ticket } from "@/types/ticket";

export function ChatPage() {
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const { sendMessage, cancelGeneration, isConnected, connectionState } = useWebSocket();

  const {
    conversations,
    currentConversationId,
    messages,
    streamingTokens,
    isStreaming,
    intent,
    sources,
    isLoadingConversations,
    isLoadingMessages,
    fetchConversations,
    selectConversation,
    createConversation,
    addUserMessage,
    resetStreaming,
  } = useChatStore();

  const [input, setInput] = useState("");
  const [isTicketDialogOpen, setIsTicketDialogOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  useEffect(() => {
    if (conversationId) {
      selectConversation(conversationId);
    }
  }, [conversationId, selectConversation]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingTokens]);

  const handleNewConversation = async () => {
    resetStreaming();
    const conversation = await createConversation();
    navigate(`/app/chat/${conversation.id}`);
  };

  const handleSelectConversation = (id: string) => {
    resetStreaming();
    navigate(`/app/chat/${id}`);
  };

  const handleSend = async () => {
    const content = input.trim();
    if (!content || isStreaming || !isConnected) return;

    let nextConversationId = currentConversationId;
    if (!nextConversationId) {
      const conversation = await createConversation();
      nextConversationId = conversation.id;
      navigate(`/app/chat/${conversation.id}`, { replace: true });
    }

    const sent = sendMessage(nextConversationId, content);
    if (!sent) return;

    addUserMessage(nextConversationId, content);
    setInput("");
  };

  const handleTicketCreated = (ticket: Ticket) => {
    navigate(`/app/tickets/${ticket.id}`);
  };

  const currentMessages = currentConversationId
    ? (messages[currentConversationId] ?? [])
    : [];
  const currentConversation =
    conversations.find((conversation) => conversation.id === currentConversationId) ?? null;
  const canCreateTicket = Boolean(currentConversationId && currentMessages.length > 0);
  const connectionHint =
    connectionState === "connecting"
      ? "正在连接聊天服务，连接完成后才能发送消息。"
      : connectionState === "reconnecting"
        ? "连接已中断，正在重连，请稍候。"
        : connectionState === "idle"
          ? "聊天连接不可用，请稍后重试。"
          : null;

  return (
    <>
      <div className="flex h-full">
        <ConversationList
          conversations={conversations}
          currentConversationId={currentConversationId}
          isLoading={isLoadingConversations}
          onCreate={handleNewConversation}
          onSelect={handleSelectConversation}
        />

        <div className="flex flex-1 flex-col">
          <div className="flex-1 space-y-4 overflow-auto p-4">
            <MessageList
              messages={currentMessages}
              streamingTokens={streamingTokens}
              isLoading={isLoadingMessages}
              endRef={messagesEndRef}
            />
          </div>

          <ChatComposer
            input={input}
            isStreaming={isStreaming}
            canSend={Boolean(input.trim()) && isConnected && !isStreaming}
            connectionHint={connectionHint}
            onInputChange={setInput}
            onSend={handleSend}
            onCancel={cancelGeneration}
          />
        </div>

        <ChatInfoPanel
          intent={intent}
          sources={sources}
          canCreateTicket={canCreateTicket}
          onCreateTicket={() => setIsTicketDialogOpen(true)}
        />
      </div>

      <CreateTicketDialog
        open={isTicketDialogOpen}
        conversationId={currentConversationId}
        conversationTitle={currentConversation?.title ?? null}
        intentLabel={intent?.label ?? null}
        messages={currentMessages}
        onClose={() => setIsTicketDialogOpen(false)}
        onCreated={handleTicketCreated}
      />
    </>
  );
}
