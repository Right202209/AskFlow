import { useEffect, useState } from "react";
import { Link } from "react-router";
import { Loader2 } from "lucide-react";
import { useTicketStore } from "@/stores/ticketStore";
import { cn } from "@/lib/utils";
import type { TicketStatus } from "@/types/ticket";

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

export function TicketsPage() {
  const { tickets, isLoading, fetchTickets } = useTicketStore();
  const [filter, setFilter] = useState<TicketStatus | "all">("all");

  useEffect(() => {
    fetchTickets();
  }, [fetchTickets]);

  const filtered = filter === "all"
    ? tickets
    : tickets.filter((t) => t.status === filter);

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-semibold">我的工单</h1>

      {/* Filters */}
      <div className="flex gap-1">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={cn(
              "rounded-md px-3 py-1.5 text-sm transition-colors",
              filter === f.value
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-accent",
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="flex justify-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : filtered.length === 0 ? (
        <p className="py-20 text-center text-sm text-muted-foreground">暂无工单</p>
      ) : (
        <div className="overflow-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="px-4 py-3 text-left font-medium">标题</th>
                <th className="px-4 py-3 text-left font-medium">类型</th>
                <th className="px-4 py-3 text-left font-medium">状态</th>
                <th className="px-4 py-3 text-left font-medium">优先级</th>
                <th className="px-4 py-3 text-left font-medium">创建时间</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((ticket) => (
                <tr key={ticket.id} className="border-b transition-colors hover:bg-muted/50">
                  <td className="px-4 py-3">
                    <Link
                      to={`/app/tickets/${ticket.id}`}
                      className="font-medium text-primary hover:underline"
                    >
                      {ticket.title}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{ticket.ticket_type}</td>
                  <td className="px-4 py-3">
                    <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", STATUS_COLORS[ticket.status])}>
                      {STATUS_LABELS[ticket.status]}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{ticket.priority}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(ticket.created_at).toLocaleDateString()}
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
