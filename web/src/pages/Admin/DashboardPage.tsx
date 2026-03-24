import { useEffect } from "react";
import { Loader2, MessageSquare, FileText, Ticket, BookOpen } from "lucide-react";
import { useAdminStore } from "@/stores/adminStore";
import {
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";

const PIE_COLORS = ["#f59e0b", "#3b82f6", "#22c55e", "#6b7280"];

export function DashboardPage() {
  const { analytics, isLoading, fetchAnalytics } = useAdminStore();

  useEffect(() => {
    fetchAnalytics();
  }, [fetchAnalytics]);

  if (isLoading || !analytics) {
    return (
      <div className="flex justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const ticketData = Object.entries(analytics.tickets_by_status).map(([name, value]) => ({
    name,
    value,
  }));

  const intentData = Object.entries(analytics.intent_distribution).map(([name, value]) => ({
    name,
    value,
  }));

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-semibold">数据看板</h1>

      {/* Stat cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard icon={MessageSquare} label="会话总数" value={analytics.total_conversations} />
        <StatCard icon={BookOpen} label="消息总数" value={analytics.total_messages} />
        <StatCard icon={Ticket} label="工单总数" value={analytics.total_tickets} />
        <StatCard icon={FileText} label="文档总数" value={analytics.total_documents} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Ticket status distribution */}
        <div className="rounded-lg border p-4">
          <h3 className="text-sm font-medium">工单状态分布</h3>
          {ticketData.length > 0 ? (
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie data={ticketData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label>
                  {ticketData.map((_, i) => (
                    <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <p className="py-12 text-center text-sm text-muted-foreground">暂无数据</p>
          )}
        </div>

        {/* Intent distribution */}
        <div className="rounded-lg border p-4">
          <h3 className="text-sm font-medium">意图分布</h3>
          {intentData.length > 0 ? (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={intentData}>
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="value" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="py-12 text-center text-sm text-muted-foreground">暂无数据</p>
          )}
        </div>
      </div>

      {/* Average confidence */}
      <div className="rounded-lg border p-4">
        <h3 className="text-sm font-medium">平均置信度</h3>
        <p className="mt-2 text-3xl font-bold">{(analytics.avg_confidence * 100).toFixed(1)}%</p>
      </div>
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number;
}) {
  return (
    <div className="rounded-lg border p-4">
      <div className="flex items-center gap-3">
        <div className="rounded-md bg-primary/10 p-2">
          <Icon className="h-4 w-4 text-primary" />
        </div>
        <div>
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="text-2xl font-bold">{value.toLocaleString()}</p>
        </div>
      </div>
    </div>
  );
}
