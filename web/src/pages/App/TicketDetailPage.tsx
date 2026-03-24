import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router";
import { ArrowLeft, Loader2 } from "lucide-react";
import { useTicketStore } from "@/stores/ticketStore";
import { useAuthStore } from "@/stores/authStore";
import * as ticketService from "@/services/ticket";
import { cn } from "@/lib/utils";
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
  const { currentTicket, isLoading, fetchTicket, clearCurrent } = useTicketStore();
  const role = useAuthStore((s) => s.role);
  const [updating, setUpdating] = useState(false);

  useEffect(() => {
    if (ticketId) fetchTicket(ticketId);
    return () => clearCurrent();
  }, [ticketId, fetchTicket, clearCurrent]);

  const canEdit = role === "agent" || role === "admin";

  const handleStatusChange = async (status: TicketStatus) => {
    if (!ticketId || !currentTicket) return;
    setUpdating(true);
    try {
      await ticketService.updateTicket(ticketId, { status });
      fetchTicket(ticketId);
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
    <div className="p-6 space-y-6">
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
        {/* Main info */}
        <div className="space-y-4 lg:col-span-2">
          <div className="rounded-lg border p-4 space-y-3">
            <div>
              <span className="text-xs font-medium text-muted-foreground">类型</span>
              <p className="text-sm">{currentTicket.ticket_type}</p>
            </div>
            <div>
              <span className="text-xs font-medium text-muted-foreground">描述</span>
              <p className="whitespace-pre-wrap text-sm">{currentTicket.content}</p>
            </div>
            {currentTicket.extra && Object.keys(currentTicket.extra).length > 0 && (
              <div>
                <span className="text-xs font-medium text-muted-foreground">附加信息</span>
                <pre className="mt-1 rounded bg-muted p-2 text-xs overflow-auto">
                  {JSON.stringify(currentTicket.extra, null, 2)}
                </pre>
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

        {/* Sidebar */}
        <div className="space-y-4">
          <div className="rounded-lg border p-4 space-y-3">
            <div>
              <span className="text-xs font-medium text-muted-foreground">状态</span>
              {canEdit ? (
                <select
                  value={currentTicket.status}
                  onChange={(e) => handleStatusChange(e.target.value as TicketStatus)}
                  disabled={updating}
                  className="mt-1 flex h-9 w-full rounded-md border bg-transparent px-3 text-sm"
                >
                  {STATUS_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              ) : (
                <p className={cn("mt-1 inline-block rounded-full px-2 py-0.5 text-xs font-medium",
                  currentTicket.status === "pending" && "bg-yellow-100 text-yellow-800",
                  currentTicket.status === "processing" && "bg-blue-100 text-blue-800",
                  currentTicket.status === "resolved" && "bg-green-100 text-green-800",
                  currentTicket.status === "closed" && "bg-gray-100 text-gray-800",
                )}>
                  {STATUS_OPTIONS.find((o) => o.value === currentTicket.status)?.label}
                </p>
              )}
            </div>
            <div>
              <span className="text-xs font-medium text-muted-foreground">优先级</span>
              <p className="text-sm">{currentTicket.priority}</p>
            </div>
            <div>
              <span className="text-xs font-medium text-muted-foreground">创建时间</span>
              <p className="text-sm">{new Date(currentTicket.created_at).toLocaleString()}</p>
            </div>
            <div>
              <span className="text-xs font-medium text-muted-foreground">更新时间</span>
              <p className="text-sm">{new Date(currentTicket.updated_at).toLocaleString()}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
