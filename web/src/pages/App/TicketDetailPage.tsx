import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { ArrowLeft, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import * as ticketService from "@/services/ticket";
import { useAuthStore } from "@/stores/authStore";
import { useTicketStore } from "@/stores/ticketStore";
import { toastError, toastSuccess } from "@/stores/toastStore";
import type { TicketStatus } from "@/types/ticket";

const STATUS_OPTIONS: Array<{ label: string; value: TicketStatus }> = [
  { label: "待处理", value: "pending" },
  { label: "处理中", value: "processing" },
  { label: "已解决", value: "resolved" },
  { label: "已关闭", value: "closed" },
];

export function TicketDetailPage() {
  const { ticketId } = useParams();
  const navigate = useNavigate();
  const currentTicket = useTicketStore((state) => state.currentTicket);
  const isLoading = useTicketStore((state) => state.isLoading);
  const fetchTicket = useTicketStore((state) => state.fetchTicket);
  const clearCurrent = useTicketStore((state) => state.clearCurrent);
  const role = useAuthStore((state) => state.role);
  const userId = useAuthStore((state) => state.userId);
  const [updating, setUpdating] = useState(false);

  useEffect(() => {
    if (ticketId) fetchTicket(ticketId);
    return () => clearCurrent();
  }, [ticketId, fetchTicket, clearCurrent]);

  const canEdit = role === "agent" || role === "admin";
  const canCloseOwnTicket =
    role === "user" &&
    userId === currentTicket?.user_id &&
    currentTicket?.status !== "closed";

  const handleStatusChange = async (status: TicketStatus) => {
    if (!ticketId || !currentTicket) return;

    setUpdating(true);
    try {
      await ticketService.updateTicket(ticketId, { status });
      await fetchTicket(ticketId);
      toastSuccess("工单状态已更新");
    } catch (error) {
      toastError(
        "更新失败",
        error instanceof Error ? error.message : "更新工单状态时发生错误",
      );
    } finally {
      setUpdating(false);
    }
  };

  if (isLoading || !currentTicket) {
    return (
      <div className="flex justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate("/app/tickets")}
          className="rounded-md p-1.5 hover:bg-accent"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <h1 className="text-xl font-semibold">{currentTicket.title}</h1>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <div className="space-y-3 rounded-lg border p-4">
            <div>
              <span className="text-xs font-medium text-muted-foreground">类型</span>
              <p className="text-sm">{currentTicket.type}</p>
            </div>
            <div>
              <span className="text-xs font-medium text-muted-foreground">描述</span>
              <p className="whitespace-pre-wrap text-sm">
                {currentTicket.description || "暂无描述"}
              </p>
            </div>
            {currentTicket.content && Object.keys(currentTicket.content).length > 0 && (
              <div>
                <span className="text-xs font-medium text-muted-foreground">附加信息</span>
                <div className="mt-1 rounded-md border bg-muted/30 p-3 text-sm flex flex-col gap-2">
                  {Object.entries(currentTicket.content).map(([key, value]) => (
                    <div key={key} className="flex flex-col sm:flex-row sm:gap-4 border-b last:border-0 pb-2 last:pb-0">
                      <span className="font-medium text-muted-foreground sm:w-1/4 shrink-0 capitalize">{key.replace(/_/g, ' ')}</span>
                      <span className="break-words sm:w-3/4">
                        {typeof value === "object" ? (
                          <pre className="whitespace-pre-wrap text-xs bg-muted/50 p-2 rounded">
                            {JSON.stringify(value, null, 2)}
                          </pre>
                        ) : (
                          String(value)
                        )}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {currentTicket.conversation_id && (
              <div>
                <span className="text-xs font-medium text-muted-foreground">关联会话</span>
                <Link
                  to={`/app/chat/${currentTicket.conversation_id}`}
                  className="block text-sm text-primary hover:underline"
                >
                  查看会话
                </Link>
              </div>
            )}
          </div>
        </div>

        <div className="space-y-4">
          <div className="space-y-3 rounded-lg border p-4">
            <div>
              <span className="text-xs font-medium text-muted-foreground">状态</span>
              {canEdit ? (
                <select
                  value={currentTicket.status}
                  onChange={(event) => handleStatusChange(event.target.value as TicketStatus)}
                  disabled={updating}
                  className="mt-1 flex h-9 w-full rounded-md border bg-transparent px-3 text-sm"
                >
                  {STATUS_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              ) : (
                <div className="mt-1 space-y-2">
                  <p
                    className={cn(
                      "inline-block rounded-full px-2 py-0.5 text-xs font-medium",
                      currentTicket.status === "pending" && "bg-yellow-100 text-yellow-800",
                      currentTicket.status === "processing" && "bg-blue-100 text-blue-800",
                      currentTicket.status === "resolved" && "bg-green-100 text-green-800",
                      currentTicket.status === "closed" && "bg-gray-100 text-gray-800",
                    )}
                  >
                    {STATUS_OPTIONS.find((option) => option.value === currentTicket.status)?.label}
                  </p>
                  {canCloseOwnTicket && (
                    <div className="space-y-2">
                      <button
                        type="button"
                        onClick={() => handleStatusChange("closed")}
                        disabled={updating}
                        className="inline-flex h-9 items-center justify-center rounded-md border px-3 text-sm hover:bg-accent disabled:opacity-50"
                      >
                        关闭工单
                      </button>
                      <p className="text-xs text-muted-foreground">
                        普通用户可以关闭自己的工单。
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
            <div>
              <span className="text-xs font-medium text-muted-foreground">优先级</span>
              <p className="text-sm">{currentTicket.priority}</p>
            </div>
            <div>
              <span className="text-xs font-medium text-muted-foreground">指派人</span>
              <p className="text-sm">{currentTicket.assignee || "未指派"}</p>
            </div>
            <div>
              <span className="text-xs font-medium text-muted-foreground">创建时间</span>
              <p className="text-sm">
                {new Date(currentTicket.created_at).toLocaleString("zh-CN")}
              </p>
            </div>
            <div>
              <span className="text-xs font-medium text-muted-foreground">解决时间</span>
              <p className="text-sm">
                {currentTicket.resolved_at
                  ? new Date(currentTicket.resolved_at).toLocaleString("zh-CN")
                  : "未解决"}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
