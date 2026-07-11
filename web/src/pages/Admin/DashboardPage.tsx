import { useEffect } from "react";
import { Loader2, MessageSquare, FileText, Ticket, BookOpen } from "lucide-react";
import { useAdminStore } from "@/stores/adminStore";
import { SystemHealthPanel } from "@/components/admin/SystemHealthPanel";
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
  const { analytics, isLoading, error, fetchAnalytics } = useAdminStore();

  useEffect(() => {
    fetchAnalytics();
  }, [fetchAnalytics]);

  if (isLoading) {
    return (
      <div className="flex justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      </div>
    );
  }

  if (!analytics) {
    return (
      <div className="p-6 text-sm text-muted-foreground">
        暂无数据
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

  const reasonData = Object.entries(analytics.harness_reason_distribution ?? {})
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value);
  const flagData = Object.entries(analytics.harness_flag_distribution ?? {})
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value);

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-semibold">数据看板</h1>

      {/* Slice 04：系统健康面板——依赖探活、文档积压、索引新鲜度、版本。 */}
      <SystemHealthPanel />

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

      {/* Task 3: harness/feedback 三项可信质量指标 */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div className="rounded-lg border p-4">
          <h3 className="text-sm font-medium">Harness Fallback Rate</h3>
          <p className="mt-2 text-3xl font-bold">
            {(analytics.harness_fallback_rate * 100).toFixed(1)}%
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            assistant 消息中 harness 走兜底逻辑的比例
          </p>
        </div>
        <div className="rounded-lg border p-4">
          <h3 className="text-sm font-medium">Harness Truncate Rate</h3>
          <p className="mt-2 text-3xl font-bold">
            {(analytics.harness_truncate_rate * 100).toFixed(1)}%
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            响应被 max_response_chars 截断的比例
          </p>
        </div>
        <div className="rounded-lg border p-4">
          <h3 className="text-sm font-medium">Thumbs Down (7d)</h3>
          <p className="mt-2 text-3xl font-bold">
            {(analytics.thumbs_down_rate_7d * 100).toFixed(1)}%
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            最近 7 天的差评率 ({analytics.feedback_total_7d} 条反馈)
          </p>
        </div>
      </div>

      {/* Phase 2 项 10:harness 拦截按 reason / flag 分类型,定位"哪类拦截在涨"。 */}
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-lg border p-4">
          <h3 className="text-sm font-medium">Harness 拦截原因分布</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            按 harness_trace.reason 聚合(assistant 消息)。
          </p>
          {reasonData.length > 0 ? (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={reasonData} layout="vertical" margin={{ left: 24 }}>
                <XAxis type="number" tick={{ fontSize: 12 }} allowDecimals={false} />
                <YAxis type="category" dataKey="name" width={140} tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="value" fill="#ef4444" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="py-12 text-center text-sm text-muted-foreground">暂无拦截</p>
          )}
        </div>

        <div className="rounded-lg border p-4">
          <h3 className="text-sm font-medium">Harness 拦截标志分布</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            按 harness_trace.flags[] 展平聚合,一条消息可命中多项。
          </p>
          {flagData.length > 0 ? (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={flagData} layout="vertical" margin={{ left: 24 }}>
                <XAxis type="number" tick={{ fontSize: 12 }} allowDecimals={false} />
                <YAxis type="category" dataKey="name" width={180} tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="value" fill="#a855f7" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="py-12 text-center text-sm text-muted-foreground">暂无标志</p>
          )}
        </div>
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
