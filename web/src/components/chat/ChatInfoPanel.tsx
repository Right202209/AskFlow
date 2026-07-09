import { FileWarning } from "lucide-react";
import { SourceCard } from "@/components/chat/SourceCard";
import type { Source } from "@/types/chat";

interface ChatInfoPanelProps {
  intent: { label: string; confidence: number } | null;
  sources: Source[];
  canCreateTicket: boolean;
  onCreateTicket: () => void;
}

export function ChatInfoPanel({
  intent,
  sources,
  canCreateTicket,
  onCreateTicket,
}: ChatInfoPanelProps) {
  return (
    <div className="hidden w-64 flex-col border-l lg:flex">
      <div className="flex h-14 items-center border-b px-4">
        <span className="text-sm font-medium">信息</span>
      </div>
      <div className="flex-1 space-y-4 overflow-auto p-4">
        <div className="rounded-lg border p-3">
          <button
            onClick={onCreateTicket}
            disabled={!canCreateTicket}
            className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <FileWarning className="h-4 w-4" />
            创建工单
          </button>
          <p className="mt-2 text-xs text-muted-foreground">
            {canCreateTicket
              ? "将当前会话的上下文提交给人工处理。"
              : "发送消息后，才能基于当前会话创建工单。"}
          </p>
        </div>

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
              {sources.map((source, index) => (
                <SourceCard key={`${source.title}-${index}`} source={source} />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
