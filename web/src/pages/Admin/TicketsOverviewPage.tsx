import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { Loader2, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import * as adminService from "@/services/admin";
import type { Ticket, TicketStatus } from "@/types/ticket";

const STATUS_LABELS: Record<TicketStatus, string> = {
  pending: "待处理",
  processing: "处理中",
  resolved: "已解决",
  closed: "已关闭",
};

const STATUS_COLORS: Record<TicketStatus, string> = {
  pending: "bg-yellow-100 text-yellow-800",
  processing: "bg-blue-100 text-blue-800",
  resolved: "bg-green-100 text-green-800",
  closed: "bg-gray-100 text-gray-800",
};

const FILTERS: Array<{ label: string; value: TicketStatus | "all" }> = [
  { label: "全部", value: "all" },
  { label: "待处理", value: "pending" },
  { label: "处理中", value: "processing" },
  { label: "已解决", value: "resolved" },
  { label: "已关闭", value: "closed" },
];

const STATUS_FILTERS: Array<{ label: string; value: TicketStatus }> = [
  { label: "待处理", value: "pending" },
  { label: "处理中", value: "processing" },
  { label: "已解决", value: "resolved" },
  { label: "已关闭", value: "closed" },
];

export function TicketsOverviewPage() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [statusFilter, setStatusFilter] = useState<TicketStatus | "all">("all");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadTickets = async (status?: TicketStatus) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await adminService.getAdminTickets(50, 0, status);
      setTickets(data);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "加载工单失败");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadTickets(statusFilter === "all" ? undefined : statusFilter);
  }, [statusFilter]);

  const summary = useMemo(() => {
    return tickets.reduce<Record<TicketStatus, number>>(
      (acc, ticket) => {
        acc[ticket.status] += 1;
        return acc;
      },
      { pending: 0, processing: 0, resolved: 0, closed: 0 },
    );
  }, [tickets]);

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">工单总览</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            查看全部工单，并快速跳转到详情页处理。
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadTickets(statusFilter === "all" ? undefined : statusFilter)}
          disabled={isLoading}
          className="inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm hover:bg-accent disabled:opacity-50"
        >
          <RefreshCw className={cn("h-4 w-4", isLoading && "animate-spin")} />
          刷新
        </button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {STATUS_FILTERS.map((item) => (
          <div key={item.value} className="rounded-lg border p-4">
            <p className="text-xs text-muted-foreground">{item.label}</p>
            <p className="mt-2 text-2xl font-semibold">{summary[item.value]}</p>
          </div>
        ))}
      </div>

      <div className="flex gap-1">
        {FILTERS.map((item) => (
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
      ) : tickets.length === 0 ? (
        <p className="py-20 text-center text-sm text-muted-foreground">暂无工单</p>
      ) : (
        <div className="overflow-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="px-4 py-3 text-left font-medium">标题</th>
                <th className="px-4 py-3 text-left font-medium">状态</th>
                <th className="px-4 py-3 text-left font-medium">优先级</th>
                <th className="px-4 py-3 text-left font-medium">类型</th>
                <th className="px-4 py-3 text-left font-medium">用户 ID</th>
                <th className="px-4 py-3 text-left font-medium">指派人</th>
                <th className="px-4 py-3 text-left font-medium">创建时间</th>
              </tr>
            </thead>
            <tbody>
              {tickets.map((ticket) => (
                <tr key={ticket.id} className="border-b transition-colors hover:bg-muted/50">
                  <td className="px-4 py-3">
                    <Link
                      to={`/app/tickets/${ticket.id}`}
                      className="font-medium text-primary hover:underline"
                    >
                      {ticket.title}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={cn(
                        "rounded-full px-2 py-0.5 text-xs font-medium",
                        STATUS_COLORS[ticket.status],
                      )}
                    >
                      {STATUS_LABELS[ticket.status]}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{ticket.priority}</td>
                  <td className="px-4 py-3 text-muted-foreground">{ticket.type}</td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">{ticket.user_id}</td>
                  <td className="px-4 py-3 text-muted-foreground">{ticket.assignee || "未指派"}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(ticket.created_at).toLocaleString("zh-CN")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
