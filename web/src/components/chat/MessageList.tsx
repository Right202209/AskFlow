import type { RefObject } from "react";
import { Loader2 } from "lucide-react";
import { MessageBubble } from "@/components/chat/MessageBubble";
import type { Message } from "@/types/chat";

interface MessageListProps {
  messages: Message[];
  streamingTokens: string;
  isLoading: boolean;
  endRef: RefObject<HTMLDivElement | null>;
}

export function MessageList({
  messages,
  streamingTokens,
  isLoading,
  endRef,
}: MessageListProps) {
  if (isLoading) {
    return (
      <div className="flex justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (messages.length === 0 && !streamingTokens) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <h3 className="text-lg font-medium">开始对话</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            输入你的问题，AI 会优先检索知识库并给出答案。
          </p>
        </div>
      </div>
    );
  }

  return (
    <>
      {messages.map((message) => (
        <MessageBubble
          key={message.id}
          role={message.role}
          content={message.content}
          sources={message.sources?.sources ?? null}
        />
      ))}
      {streamingTokens && (
        <MessageBubble
          role="assistant"
          content={streamingTokens}
          isStreaming
        />
      )}
      <div ref={endRef} />
    </>
  );
}
