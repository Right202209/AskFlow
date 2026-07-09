import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Loader2 } from "lucide-react";
import * as ticketService from "@/services/ticket";
import { toastError, toastSuccess } from "@/stores/toastStore";
import type { Message } from "@/types/chat";
import type { Ticket, TicketPriority } from "@/types/ticket";

const TYPE_OPTIONS = [
  { value: "fault_report", label: "故障反馈" },
  { value: "complaint", label: "投诉建议" },
  { value: "general_support", label: "人工协助" },
] as const;

const PRIORITY_OPTIONS: Array<{ value: TicketPriority; label: string }> = [
  { value: "low", label: "低" },
  { value: "medium", label: "中" },
  { value: "high", label: "高" },
  { value: "urgent", label: "紧急" },
];

interface CreateTicketDialogProps {
  open: boolean;
  conversationId: string | null;
  conversationTitle: string | null;
  intentLabel: string | null;
  messages: Message[];
  onClose: () => void;
  onCreated: (ticket: Ticket) => void;
}

function buildDefaultTitle(
  conversationTitle: string | null,
  lastUserMessage: string | null,
) {
  const source = conversationTitle?.trim() || lastUserMessage?.trim() || "需要人工处理";
  return source.length > 40 ? `${source.slice(0, 40)}...` : source;
}

function buildDefaultType(intentLabel: string | null) {
  if (intentLabel === "fault_report") return "fault_report";
  if (intentLabel === "complaint") return "complaint";
  return "general_support";
}

export function CreateTicketDialog({
  open,
  conversationId,
  conversationTitle,
  intentLabel,
  messages,
  onClose,
  onCreated,
}: CreateTicketDialogProps) {
  const [title, setTitle] = useState("");
  const [type, setType] = useState("general_support");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState<TicketPriority>("medium");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const previousOpenRef = useRef(false);
  const previousConversationIdRef = useRef<string | null>(null);

  useEffect(() => {
    const opened = open && !previousOpenRef.current;
    const conversationChanged =
      open &&
      previousOpenRef.current &&
      previousConversationIdRef.current !== conversationId;

    if (opened || conversationChanged) {
      const lastUserMessage =
        [...messages].reverse().find((message) => message.role === "user")?.content ?? null;

      setTitle(buildDefaultTitle(conversationTitle, lastUserMessage));
      setType(buildDefaultType(intentLabel));
      setDescription(lastUserMessage ?? "");
      setPriority("medium");
      setSubmitting(false);
      setError("");
    }

    previousOpenRef.current = open;
    previousConversationIdRef.current = conversationId;
  }, [open, conversationId, conversationTitle, intentLabel, messages]);

  if (!open) return null;

  const canSubmit = Boolean(conversationId && title.trim() && description.trim());

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!conversationId || !canSubmit) return;

    setSubmitting(true);
    setError("");

    try {
      const transcript = messages.slice(-6).map((message) => ({
        role: message.role,
        content: message.content,
        created_at: message.created_at,
      }));

      const ticket = await ticketService.createTicket({
        type,
        title: title.trim(),
        description: description.trim(),
        priority,
        conversation_id: conversationId,
        content: {
          source: "chat",
          intent: intentLabel,
          transcript,
        },
      });

      onClose();
      toastSuccess("工单创建成功", "已附带当前会话上下文。");
      onCreated(ticket);
    } catch (submitError) {
      const message = submitError instanceof Error ? submitError.message : "创建工单失败";
      setError(message);
      toastError("创建工单失败", message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
      <div className="w-full max-w-lg rounded-lg border bg-card p-6 shadow-lg">
        <h2 className="text-lg font-semibold">创建工单</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          会将当前会话的最近消息作为上下文附带到工单中。
        </p>

        {error && (
          <div className="mt-3 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          <div className="space-y-1">
            <label className="text-sm font-medium">标题</label>
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              required
              maxLength={255}
              className="flex h-10 w-full rounded-md border bg-transparent px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1">
              <label className="text-sm font-medium">类型</label>
              <select
                value={type}
                onChange={(event) => setType(event.target.value)}
                className="flex h-10 w-full rounded-md border bg-transparent px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                {TYPE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-1">
              <label className="text-sm font-medium">优先级</label>
              <select
                value={priority}
                onChange={(event) => setPriority(event.target.value as TicketPriority)}
                className="flex h-10 w-full rounded-md border bg-transparent px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                {PRIORITY_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="space-y-1">
            <label className="text-sm font-medium">描述</label>
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              required
              rows={5}
              className="w-full rounded-md border bg-transparent px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
          </div>

          <div className="rounded-md bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
            关联会话 ID: {conversationId ?? "未关联"}
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              className="rounded-md border px-4 py-2 text-sm hover:bg-accent disabled:opacity-50"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={!canSubmit || submitting}
              className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow hover:bg-primary/90 disabled:opacity-50"
            >
              {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
              创建工单
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
