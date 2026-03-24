import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router";
import { Plus, Send, Square, Loader2 } from "lucide-react";
import { useChatStore } from "@/stores/chatStore";
import { useWebSocket } from "@/hooks/useWebSocket";
import { cn } from "@/lib/utils";
import type { Source } from "@/types/chat";

export function ChatPage() {
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const { sendMessage, cancelGeneration } = useWebSocket();

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
    const conv = await createConversation();
    navigate(`/app/chat/${conv.id}`);
  };

  const handleSelectConversation = (id: string) => {
    resetStreaming();
    navigate(`/app/chat/${id}`);
  };

  const handleSend = async () => {
    if (!input.trim() || isStreaming) return;

    let convId = currentConversationId;
    if (!convId) {
      const conv = await createConversation();
      convId = conv.id;
      navigate(`/app/chat/${conv.id}`, { replace: true });
    }

    addUserMessage(convId, input.trim());
    sendMessage(convId, input.trim());
    setInput("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const currentMessages = currentConversationId
    ? (messages[currentConversationId] ?? [])
    : [];

  return (
    <div className="flex h-full">
      {/* Conversation list */}
      <div className="flex w-60 flex-col border-r">
        <div className="flex h-14 items-center justify-between border-b px-3">
          <span className="text-sm font-medium">会话</span>
          <button
            onClick={handleNewConversation}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
            title="新建会话"
          >
            <Plus className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-auto p-2 space-y-1">
          {isLoadingConversations ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : conversations.length === 0 ? (
            <p className="py-8 text-center text-xs text-muted-foreground">暂无会话</p>
          ) : (
            conversations.map((conv) => (
              <button
                key={conv.id}
                onClick={() => handleSelectConversation(conv.id)}
                className={cn(
                  "w-full rounded-md px-3 py-2 text-left text-sm transition-colors",
                  conv.id === currentConversationId
                    ? "bg-accent font-medium"
                    : "hover:bg-accent/50",
                )}
              >
                <span className="line-clamp-1">{conv.title || "新会话"}</span>
                <span className="text-xs text-muted-foreground">
                  {new Date(conv.updated_at).toLocaleDateString()}
                </span>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Chat area */}
      <div className="flex flex-1 flex-col">
        {/* Messages */}
        <div className="flex-1 overflow-auto p-4 space-y-4">
          {isLoadingMessages ? (
            <div className="flex justify-center py-20">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : currentMessages.length === 0 && !streamingTokens ? (
            <div className="flex h-full items-center justify-center">
              <div className="text-center">
                <h3 className="text-lg font-medium">开始对话</h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  输入您的问题，AI 将为您解答
                </p>
              </div>
            </div>
          ) : (
            <>
              {currentMessages.map((msg) => (
                <MessageBubble key={msg.id} role={msg.role} content={msg.content} sources={msg.sources?.sources ?? null} />
              ))}
              {streamingTokens && (
                <MessageBubble role="assistant" content={streamingTokens} isStreaming />
              )}
              <div ref={messagesEndRef} />
            </>
          )}
        </div>

        {/* Input */}
        <div className="border-t p-4">
          <div className="flex items-end gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入消息..."
              rows={1}
              className="flex-1 resize-none rounded-md border bg-transparent px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
            {isStreaming ? (
              <button
                onClick={cancelGeneration}
                className="inline-flex h-9 w-9 items-center justify-center rounded-md border text-muted-foreground hover:bg-accent"
                title="停止生成"
              >
                <Square className="h-4 w-4" />
              </button>
            ) : (
              <button
                onClick={handleSend}
                disabled={!input.trim()}
                className="inline-flex h-9 w-9 items-center justify-center rounded-md bg-primary text-primary-foreground shadow hover:bg-primary/90 disabled:opacity-50"
                title="发送"
              >
                <Send className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Info panel */}
      <div className="hidden w-64 flex-col border-l lg:flex">
        <div className="flex h-14 items-center border-b px-4">
          <span className="text-sm font-medium">信息</span>
        </div>
        <div className="flex-1 overflow-auto p-4 space-y-4">
          {intent && (
            <div>
              <p className="text-xs font-medium text-muted-foreground">意图</p>
              <div className="mt-1 inline-flex items-center rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary">
                {intent.label}
                <span className="ml-1 text-muted-foreground">
                  {(intent.confidence * 100).toFixed(0)}%
                </span>
              </div>
            </div>
          )}
          {sources.length > 0 && (
            <div>
              <p className="text-xs font-medium text-muted-foreground">来源</p>
              <div className="mt-2 space-y-2">
                {sources.map((src, i) => (
                  <SourceCard key={i} source={src} />
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function MessageBubble({
  role,
  content,
  sources,
  isStreaming,
}: {
  role: string;
  content: string;
  sources?: Source[] | null;
  isStreaming?: boolean;
}) {
  const isUser = role === "user";
  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[80%] rounded-lg px-4 py-2.5 text-sm",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted",
        )}
      >
        <p className="whitespace-pre-wrap">{content}</p>
        {isStreaming && (
          <span className="inline-block h-4 w-1 animate-pulse bg-current" />
        )}
        {sources && sources.length > 0 && (
          <div className="mt-2 space-y-1 border-t border-border/50 pt-2">
            {sources.map((src, i) => (
              <p key={i} className="text-xs opacity-70">
                [{i + 1}] {src.title} (score: {src.score.toFixed(2)})
              </p>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function SourceCard({ source }: { source: Source }) {
  return (
    <div className="rounded-md border p-2">
      <p className="text-xs font-medium">{source.title}</p>
      <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
        {source.chunk}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        相关度: {(source.score * 100).toFixed(0)}%
      </p>
    </div>
  );
}
