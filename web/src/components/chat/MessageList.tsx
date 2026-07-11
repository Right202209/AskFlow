import type { RefObject } from "react";
import { Loader2 } from "lucide-react";
import { MessageBubble } from "@/components/chat/MessageBubble";
import type { Message } from "@/types/chat";

interface MessageListProps {
  messages: Message[];
  streamingTokens: string;
  isLoading: boolean;
  endRef: RefObject<HTMLDivElement | null>;
  /** 人工接管期间 AI 不应答，挂起"AI 思考中"指示器。 */
  isTransferred?: boolean;
  onFeedback?: (messageId: string, rating: -1 | 1) => Promise<void> | void;
}

export function MessageList({
  messages,
  streamingTokens,
  isLoading,
  endRef,
  isTransferred = false,
  onFeedback,
}: MessageListProps) {
  const isAILoading =
    !isLoading &&
    !isTransferred &&
    messages.length > 0 &&
    messages[messages.length - 1]?.role === "user" &&
    !streamingTokens;

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
          messageId={message.role === "assistant" ? message.id : undefined}
          feedback={message.feedback ?? null}
          verification={message.verification ?? message.extra?.verification ?? null}
          answerConfidence={
            message.answer_confidence ?? message.extra?.answer_confidence ?? null
          }
          staffName={message.staff_name ?? null}
          onFeedback={onFeedback}
        />
      ))}
      {streamingTokens && (
        <MessageBubble
          role="assistant"
          content={streamingTokens}
          isStreaming
        />
      )}
      {isAILoading && (
        <div className="flex px-4 py-3 opacity-50">
          <div className="flex h-8 w-8 shrink-0 select-none items-center justify-center rounded-md border bg-primary text-primary-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
          </div>
          <div className="ml-4 flex items-center text-sm font-medium">
            AI 思考中...
          </div>
        </div>
      )}
      <div ref={endRef} />
    </>
  );
}
