import { memo, useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import { AlertCircle, FileText, ThumbsDown, ThumbsUp } from "lucide-react";
import type { Message, Source } from "@/types/chat";

interface MessageBubbleProps {
  role: Message["role"];
  content: string;
  sources?: Source[] | null;
  isStreaming?: boolean;
  messageId?: string;
  feedback?: -1 | 1 | null;
  onFeedback?: (messageId: string, rating: -1 | 1) => Promise<void> | void;
}

function renderContent(content: string) {
  const fallbackPrefix = "AI generation is temporarily unavailable. Here are the most relevant knowledge base excerpts:";
  
  if (content.startsWith(fallbackPrefix)) {
    const remaining = content.substring(fallbackPrefix.length).trim();
    const regex = /\*\*(\d+)\.\s+\[(.*?)\]\*\*\n([\s\S]*?)(?=(?:\*\*|$))/g;
    
    const excerpts: { id: string; title: string; text: string }[] = [];
    let match;
    while ((match = regex.exec(remaining)) !== null) {
      if (match[1] && match[2] && match[3]) {
        excerpts.push({
          id: match[1],
          title: match[2],
          text: match[3].trim()
        });
      }
    }

    if (excerpts.length > 0) {
      return (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-destructive font-medium bg-destructive/10 p-2.5 rounded-md border border-destructive/20 text-xs sm:text-sm">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>AI generation is temporarily unavailable. Displaying relevant knowledge base excerpts.</span>
          </div>
          <div className="space-y-2.5">
            {excerpts.map((excerpt) => (
              <div key={excerpt.id} className="bg-background rounded-md border border-border/60 p-3 text-sm shadow-sm">
                <div className="flex items-center gap-1.5 font-semibold text-foreground mb-1.5 pb-1.5 border-b border-border/40">
                  <FileText className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                  <span className="line-clamp-1">{excerpt.title}</span>
                </div>
                <p className="text-muted-foreground leading-relaxed text-xs sm:text-sm whitespace-pre-wrap">
                  {excerpt.text}
                </p>
              </div>
            ))}
          </div>
        </div>
      );
    }
  }

  return <p className="whitespace-pre-wrap">{content}</p>;
}

export const MessageBubble = memo(function MessageBubble({
  role,
  content,
  sources,
  isStreaming = false,
  messageId,
  feedback = null,
  onFeedback,
}: MessageBubbleProps) {
  const isUser = role === "user";
  const [submitting, setSubmitting] = useState(false);

  const renderedContent = useMemo(() => renderContent(content), [content]);

  const handleFeedback = async (rating: -1 | 1) => {
    if (!messageId || !onFeedback || submitting) return;
    setSubmitting(true);
    try {
      await onFeedback(messageId, rating);
    } finally {
      setSubmitting(false);
    }
  };

  const showFeedback = !isUser && !isStreaming && messageId && onFeedback;

  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] sm:max-w-[80%] rounded-xl px-4 py-3 text-sm flex flex-col gap-2",
          isUser ? "bg-primary text-primary-foreground" : "bg-muted text-foreground",
        )}
      >
        {renderedContent}

        {isStreaming && (
          <span className="inline-block h-4 w-1 animate-pulse bg-current mt-1" />
        )}

        {sources && sources.length > 0 && (
          <div className="mt-2 space-y-1.5 border-t border-border/50 pt-3">
            <p className="text-xs font-semibold opacity-80 mb-1">Sources</p>
            {sources.map((source, index) => (
              <div key={`${source.title}-${index}`} className="flex items-center gap-1.5 text-xs opacity-75 hover:opacity-100 transition-opacity">
                <span className="bg-background/50 rounded px-1.5 py-0.5 min-w-[1.25rem] text-center font-mono text-[10px]">
                  {index + 1}
                </span>
                <span className="truncate">{source.title}</span>
                <span className="ml-auto opacity-60 text-[10px]">
                  ({source.score.toFixed(2)})
                </span>
              </div>
            ))}
          </div>
        )}

        {showFeedback && (
          <div className="mt-1 flex items-center gap-2 pt-2 border-t border-border/40">
            <button
              type="button"
              aria-label="Mark this answer as helpful"
              disabled={submitting}
              onClick={() => handleFeedback(1)}
              className={cn(
                "p-1 rounded transition-colors disabled:opacity-50",
                feedback === 1 ? "text-green-600" : "text-muted-foreground hover:text-foreground",
              )}
            >
              <ThumbsUp className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              aria-label="Mark this answer as not helpful"
              disabled={submitting}
              onClick={() => handleFeedback(-1)}
              className={cn(
                "p-1 rounded transition-colors disabled:opacity-50",
                feedback === -1 ? "text-red-600" : "text-muted-foreground hover:text-foreground",
              )}
            >
              <ThumbsDown className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
});
