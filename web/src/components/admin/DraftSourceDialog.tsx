import { useState } from "react";
import { Loader2, X } from "lucide-react";
import { cn } from "@/lib/utils";
import * as adminService from "@/services/admin";
import type { DraftCreateRequest, KnowledgeDraft, KnowledgeGap } from "@/types/knowledge";

type SourceMode = "conversation" | "ticket" | "manual" | "blank";

interface DraftSourceDialogProps {
  gap: KnowledgeGap;
  onClose: () => void;
  onCreated: (draft: KnowledgeDraft) => void;
}

/** 缺口 → 草稿的素材选择弹窗：例会话 / 工单 ID / 手动输入 / 空白，可选 AI 辅助草拟。 */
export function DraftSourceDialog({ gap, onClose, onCreated }: DraftSourceDialogProps) {
  const hasConversation = Boolean(gap.example_conversation_id);
  const [mode, setMode] = useState<SourceMode>(hasConversation ? "conversation" : "blank");
  const [ticketId, setTicketId] = useState("");
  const [manualAnswer, setManualAnswer] = useState("");
  const [synthesize, setSynthesize] = useState(true);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const modes: Array<{ value: SourceMode; label: string; disabled?: boolean }> = [
    { value: "conversation", label: "例会话转录", disabled: !hasConversation },
    { value: "ticket", label: "工单（输入 ID）" },
    { value: "manual", label: "手动输入答案" },
    { value: "blank", label: "空白草稿" },
  ];

  const buildRequest = (): DraftCreateRequest => {
    const body: DraftCreateRequest = { synthesize };
    if (mode === "conversation" && gap.example_conversation_id) {
      body.conversation_id = gap.example_conversation_id;
    } else if (mode === "ticket" && ticketId.trim()) {
      body.ticket_id = ticketId.trim();
    } else if (mode === "manual" && manualAnswer.trim()) {
      body.manual_answer = manualAnswer.trim();
    }
    return body;
  };

  const handleSubmit = async () => {
    setIsBusy(true);
    setError(null);
    try {
      const draft = await adminService.createDraftFromGap(gap.id, buildRequest());
      onCreated(draft);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "草拟失败");
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-lg rounded-lg border bg-background p-5 shadow-lg">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-base font-semibold">草拟知识条目</h2>
            <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{gap.question}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-muted-foreground hover:bg-accent"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="mt-4 space-y-2">
          {modes.map((item) => (
            <label
              key={item.value}
              className={cn(
                "flex items-center gap-2 rounded-md border px-3 py-2 text-sm",
                item.disabled ? "opacity-40" : "cursor-pointer hover:bg-accent/50",
                mode === item.value && "border-primary bg-primary/5",
              )}
            >
              <input
                type="radio"
                name="draft-source"
                checked={mode === item.value}
                disabled={item.disabled}
                onChange={() => setMode(item.value)}
              />
              {item.label}
            </label>
          ))}
        </div>

        {mode === "ticket" && (
          <input
            value={ticketId}
            onChange={(e) => setTicketId(e.target.value)}
            placeholder="粘贴工单 ID（可在工单总览复制）"
            className="mt-3 w-full rounded-md border bg-background px-3 py-2 text-sm"
          />
        )}
        {mode === "manual" && (
          <textarea
            value={manualAnswer}
            onChange={(e) => setManualAnswer(e.target.value)}
            placeholder="输入答案内容（markdown）"
            rows={5}
            className="mt-3 w-full rounded-md border bg-background px-3 py-2 font-mono text-sm"
          />
        )}

        <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={synthesize}
            onChange={(e) => setSynthesize(e.target.checked)}
          />
          AI 辅助草拟（失败时自动回落到原始素材）
        </label>

        {error && (
          <div className="mt-3 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </div>
        )}

        <div className="mt-4 flex justify-end gap-2 border-t pt-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border px-3 py-2 text-sm hover:bg-accent"
          >
            取消
          </button>
          <button
            type="button"
            onClick={() => void handleSubmit()}
            disabled={isBusy || (mode === "ticket" && !ticketId.trim())}
            className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {isBusy && <Loader2 className="h-4 w-4 animate-spin" />}
            创建草稿
          </button>
        </div>
      </div>
    </div>
  );
}
