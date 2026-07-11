import { useEffect, useState } from "react";
import { CheckCheck, Hand, Loader2, RefreshCw, Send, Undo2 } from "lucide-react";
import { cn } from "@/lib/utils";
import * as adminService from "@/services/admin";
import { useAuthStore } from "@/stores/authStore";
import type { HandoffDetail, HandoffSession, HandoffSessionStatus } from "@/types/handoff";

const STATUS_FILTERS: Array<{ label: string; value: HandoffSessionStatus }> = [
  { label: "待认领", value: "queued" },
  { label: "处理中", value: "claimed" },
  { label: "已解决", value: "resolved" },
  { label: "已回流", value: "returned" },
  { label: "已超时", value: "timed_out" },
];

const STATUS_BADGES: Record<HandoffSessionStatus, string> = {
  queued: "bg-yellow-100 text-yellow-800",
  claimed: "bg-blue-100 text-blue-800",
  resolved: "bg-green-100 text-green-800",
  returned: "bg-teal-100 text-teal-800",
  timed_out: "bg-red-100 text-red-800",
};

const ROLE_LABELS: Record<string, string> = {
  user: "用户",
  assistant: "AI",
  staff: "客服",
  system: "系统",
};

const PAGE_SIZE = 20;

export function HandoffsPage() {
  const userId = useAuthStore((s) => s.userId);
  const [sessions, setSessions] = useState<HandoffSession[]>([]);
  const [statusFilter, setStatusFilter] = useState<HandoffSessionStatus>("queued");
  const [detail, setDetail] = useState<HandoffDetail | null>(null);
  const [reply, setReply] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadSessions = async (status: HandoffSessionStatus) => {
    setIsLoading(true);
    setError(null);
    try {
      setSessions(await adminService.getHandoffs(status, PAGE_SIZE, 0));
      setDetail(null);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "加载接管队列失败");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadSessions(statusFilter);
  }, [statusFilter]);

  const openDetail = async (session: HandoffSession) => {
    setError(null);
    try {
      setDetail(await adminService.getHandoffDetail(session.id));
    } catch (detailError) {
      setError(detailError instanceof Error ? detailError.message : "加载会话详情失败");
    }
  };

  const runAction = async (action: () => Promise<void>) => {
    setIsBusy(true);
    setError(null);
    try {
      await action();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "操作失败");
    } finally {
      setIsBusy(false);
    }
  };

  const handleClaim = (session: HandoffSession) =>
    runAction(async () => {
      await adminService.claimHandoff(session.id);
      await loadSessions(statusFilter);
    });

  const handleReply = () =>
    runAction(async () => {
      if (!detail || !reply.trim()) return;
      await adminService.replyHandoff(detail.session.id, reply.trim());
      setReply("");
      setDetail(await adminService.getHandoffDetail(detail.session.id));
    });

  const handleResolve = (status: "resolved" | "returned") =>
    runAction(async () => {
      if (!detail) return;
      await adminService.resolveHandoff(detail.session.id, status);
      await loadSessions(statusFilter);
    });

  const isMine = detail?.session.assignee === userId;
  const canOperate = detail?.session.status === "claimed" && isMine;

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">人工接管</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            转接队列：认领后接管对话，回复用户，处理完暖回流给 AI。
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadSessions(statusFilter)}
          disabled={isLoading}
          className="inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm hover:bg-accent disabled:opacity-50"
        >
          <RefreshCw className={cn("h-4 w-4", isLoading && "animate-spin")} />
          刷新
        </button>
      </div>

      <div className="flex gap-1">
        {STATUS_FILTERS.map((item) => (
          <button
            key={item.value}
            type="button"
            onClick={() => setStatusFilter(item.value)}
            className={cn(
              "rounded-md px-3 py-1.5 text-sm transition-colors",
              statusFilter === item.value
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-accent",
            )}
          >
            {item.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {isLoading ? (
        <div className="flex justify-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(300px,1fr)_2fr]">
          <div className="overflow-auto rounded-lg border">
            {sessions.length === 0 ? (
              <p className="py-16 text-center text-sm text-muted-foreground">队列为空</p>
            ) : (
              <ul className="divide-y">
                {sessions.map((session) => (
                  <li key={session.id} className="p-3">
                    <button
                      type="button"
                      onClick={() => void openDetail(session)}
                      className="w-full text-left"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span
                          className={cn(
                            "rounded-full px-2 py-0.5 text-xs font-medium",
                            STATUS_BADGES[session.status],
                          )}
                        >
                          {STATUS_FILTERS.find((f) => f.value === session.status)?.label}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {new Date(session.created_at).toLocaleString("zh-CN")}
                        </span>
                      </div>
                      <p className="mt-2 line-clamp-2 text-sm">
                        {session.summary || "（摘要生成失败，请查看完整转录）"}
                      </p>
                    </button>
                    {session.status === "queued" && (
                      <button
                        type="button"
                        onClick={() => void handleClaim(session)}
                        disabled={isBusy}
                        className="mt-2 inline-flex items-center gap-1.5 rounded-md bg-primary px-2.5 py-1 text-xs text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                      >
                        <Hand className="h-3 w-3" /> 认领
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="flex flex-col rounded-lg border">
            {!detail ? (
              <p className="py-16 text-center text-sm text-muted-foreground">
                从左侧选择一条接管会话
              </p>
            ) : (
              <>
                <div className="border-b p-4">
                  <p className="text-sm font-medium">摘要</p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {detail.session.summary || "（摘要生成失败）"}
                  </p>
                  {(detail.session.payload.intent_history?.length ?? 0) > 0 && (
                    <p className="mt-1 text-xs text-muted-foreground">
                      意图路径：{detail.session.payload.intent_history!.join(" → ")}
                    </p>
                  )}
                </div>
                <div className="max-h-96 flex-1 space-y-2 overflow-auto p-4">
                  {detail.messages.map((message) => (
                    <div
                      key={message.id}
                      className={cn(
                        "rounded-md px-3 py-2 text-sm",
                        message.role === "user" ? "bg-primary/10" : "bg-muted",
                      )}
                    >
                      <span className="mr-2 text-xs font-semibold text-muted-foreground">
                        {ROLE_LABELS[message.role] ?? message.role}
                      </span>
                      <span className="whitespace-pre-wrap">{message.content}</span>
                    </div>
                  ))}
                </div>
                {canOperate && (
                  <div className="space-y-2 border-t p-4">
                    <div className="flex gap-2">
                      <input
                        value={reply}
                        onChange={(e) => setReply(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && void handleReply()}
                        placeholder="回复用户…"
                        className="flex-1 rounded-md border bg-background px-3 py-2 text-sm"
                      />
                      <button
                        type="button"
                        onClick={() => void handleReply()}
                        disabled={isBusy || !reply.trim()}
                        className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                      >
                        <Send className="h-4 w-4" /> 发送
                      </button>
                    </div>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => void handleResolve("resolved")}
                        disabled={isBusy}
                        className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs hover:bg-accent disabled:opacity-50"
                      >
                        <CheckCheck className="h-3.5 w-3.5" /> 标记解决
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleResolve("returned")}
                        disabled={isBusy}
                        className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs hover:bg-accent disabled:opacity-50"
                      >
                        <Undo2 className="h-3.5 w-3.5" /> 交还 AI
                      </button>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
