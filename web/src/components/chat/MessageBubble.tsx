import { memo, useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import { AlertCircle, FileText, Headphones, ThumbsDown, ThumbsUp } from "lucide-react";
import type { AnswerConfidence, Message, Source, Verification } from "@/types/chat";
import { renderWithCitations } from "@/lib/citations";
import { ConfidenceBadge } from "@/components/chat/ConfidenceBadge";
import { SourceCard } from "@/components/chat/SourceCard";

interface MessageBubbleProps {
  role: Message["role"];
  content: string;
  sources?: Source[] | null;
  isStreaming?: boolean;
  messageId?: string;
  feedback?: -1 | 1 | null;
  verification?: Verification | null;
  answerConfidence?: AnswerConfidence | null;
  /** staff 消息展示的客服名（staff_message 帧 / 历史回放）。 */
  staffName?: string | null;
  onFeedback?: (messageId: string, rating: -1 | 1) => Promise<void> | void;
}

const LLM_FALLBACK_PREFIX =
  "AI generation is temporarily unavailable. Here are the most relevant knowledge base excerpts:";

function renderLlmFallback(content: string) {
  const remaining = content.substring(LLM_FALLBACK_PREFIX.length).trim();
  const regex = /\*\*(\d+)\.\s+\[(.*?)\]\*\*\n([\s\S]*?)(?=(?:\*\*|$))/g;

  const excerpts: { id: string; title: string; text: string }[] = [];
  let match;
  while ((match = regex.exec(remaining)) !== null) {
    if (match[1] && match[2] && match[3]) {
      excerpts.push({ id: match[1], title: match[2], text: match[3].trim() });
    }
  }
  if (excerpts.length === 0) return null;

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

function VerificationBadge({ verification }: { verification: Verification }) {
  if (!verification.checked || verification.verdict === "skipped") return null;
  const meta = {
    pass: { icon: "✓", text: "自检通过", className: "text-green-600" },
    partial: { icon: "⚠", text: "自检部分通过", className: "text-amber-600" },
    fail: { icon: "✗", text: "自检未通过", className: "text-red-600" },
  }[verification.verdict as "pass" | "partial" | "fail"];
  if (!meta) return null;

  return (
    <p className={cn("text-[10px] font-medium", meta.className)}>
      {meta.icon} {meta.text}：{verification.supported}/{verification.total} 条引用有据可依
      {verification.invalid_citations.length > 0 &&
        `（越界标记 ${verification.invalid_citations.map((n) => `[${n}]`).join(" ")}）`}
    </p>
  );
}

export const MessageBubble = memo(function MessageBubble({
  role,
  content,
  sources,
  isStreaming = false,
  messageId,
  feedback = null,
  verification = null,
  answerConfidence = null,
  staffName = null,
  onFeedback,
}: MessageBubbleProps) {
  const isUser = role === "user";
  const isStaff = role === "staff";
  const [submitting, setSubmitting] = useState(false);
  const [activeSource, setActiveSource] = useState<number | null>(null);

  const sourceList = sources ?? [];
  const sourceCount = sourceList.length;

  const toggleSource = (n: number) =>
    setActiveSource((prev) => (prev === n ? null : n));

  const renderedContent = useMemo(() => {
    if (content.startsWith(LLM_FALLBACK_PREFIX)) {
      const fallback = renderLlmFallback(content);
      if (fallback) return fallback;
    }
    if (isUser || sourceCount === 0) {
      return <p className="whitespace-pre-wrap">{content}</p>;
    }
    return (
      <p className="whitespace-pre-wrap">
        {renderWithCitations(content, sourceCount, {
          activeIndex: activeSource,
          onCitationClick: toggleSource,
        })}
      </p>
    );
  }, [content, isUser, sourceCount, activeSource]);

  const activeSourceItem = sourceList.find(
    (source, index) => (source.index ?? index + 1) === activeSource,
  );

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
          isUser
            ? "bg-primary text-primary-foreground"
            : isStaff
              ? "border border-amber-200 bg-amber-50 text-foreground"
              : "bg-muted text-foreground",
        )}
      >
        {isStaff && (
          <p className="flex items-center gap-1.5 text-xs font-medium text-amber-700">
            <Headphones className="h-3.5 w-3.5" />
            人工客服{staffName ? ` · ${staffName}` : ""}
          </p>
        )}
        {renderedContent}

        {isStreaming && (
          <span className="inline-block h-4 w-1 animate-pulse bg-current mt-1" />
        )}

        {activeSourceItem && <SourceCard source={activeSourceItem} />}

        {!isUser && !isStreaming && (verification || answerConfidence) && (
          <div className="flex flex-col gap-1">
            {answerConfidence && <ConfidenceBadge confidence={answerConfidence} />}
            {verification && <VerificationBadge verification={verification} />}
          </div>
        )}

        {sourceCount > 0 && (
          <div className="mt-2 space-y-1.5 border-t border-border/50 pt-3">
            <p className="text-xs font-semibold opacity-80 mb-1">Sources</p>
            {sourceList.map((source, index) => {
              const citationIndex = source.index ?? index + 1;
              return (
                <button
                  key={`${source.title}-${index}`}
                  type="button"
                  onClick={() => toggleSource(citationIndex)}
                  className={cn(
                    "flex w-full items-center gap-1.5 text-left text-xs transition-opacity",
                    activeSource === citationIndex
                      ? "opacity-100"
                      : "opacity-75 hover:opacity-100",
                  )}
                >
                  <span
                    className={cn(
                      "rounded px-1.5 py-0.5 min-w-[1.25rem] text-center font-mono text-[10px]",
                      activeSource === citationIndex
                        ? "bg-primary text-primary-foreground"
                        : "bg-background/50",
                    )}
                  >
                    {citationIndex}
                  </span>
                  <span className="truncate">{source.title}</span>
                  <span className="ml-auto opacity-60 text-[10px]">
                    ({source.score.toFixed(2)})
                  </span>
                </button>
              );
            })}
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
