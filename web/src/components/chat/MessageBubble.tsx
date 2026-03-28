import { cn } from "@/lib/utils";
import type { Message, Source } from "@/types/chat";

interface MessageBubbleProps {
  role: Message["role"];
  content: string;
  sources?: Source[] | null;
  isStreaming?: boolean;
}

export function MessageBubble({
  role,
  content,
  sources,
  isStreaming = false,
}: MessageBubbleProps) {
  const isUser = role === "user";

  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[80%] rounded-lg px-4 py-2.5 text-sm",
          isUser ? "bg-primary text-primary-foreground" : "bg-muted",
        )}
      >
        <p className="whitespace-pre-wrap">{content}</p>
        {isStreaming && (
          <span className="inline-block h-4 w-1 animate-pulse bg-current" />
        )}
        {sources && sources.length > 0 && (
          <div className="mt-2 space-y-1 border-t border-border/50 pt-2">
            {sources.map((source, index) => (
              <p key={`${source.title}-${index}`} className="text-xs opacity-70">
                [{index + 1}] {source.title} ({source.score.toFixed(2)})
              </p>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
