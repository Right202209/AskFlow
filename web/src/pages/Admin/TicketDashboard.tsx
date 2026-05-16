import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Clock,
  Inbox,
  Loader2,
  RefreshCw,
  TrendingUp,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { cn } from "@/lib/utils";
import * as adminService from "@/services/admin";
import type { TicketDashboardData } from "@/types/admin";

const PRIORITY_ORDER = ["urgent", "high", "medium", "low"] as const;
const PRIORITY_COLORS: Record<string, string> = {
  urgent: "#dc2626",
  high: "#f97316",
  medium: "#3b82f6",
  low: "#22c55e",
};

export function TicketDashboard() {
  const [data, setData] = useState<TicketDashboardData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setIsLoading(true);
    setError(null);
    try {
      setData(await adminService.getTicketDashboard());
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "加载工单看板失败");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  if (isLoading && !data) {
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

  if (!data) {
    return <div className="p-6 text-sm text-muted-foreground">暂无数据</div>;
  }

  // 按 PRIORITY_ORDER 摆稳序;后端没返回的优先级补 0,让前端柱状图始终四档。
  const priorityData = PRIORITY_ORDER.map((p) => ({
    name: p,
    value: data.open_by_priority[p] ?? 0,
  }));
  // recharts 不接受 null trend,这里转一份非 null 数值;后端已 7 天补齐。
  const trendData = data.daily_trend.map((point) => ({
    date: point.date.slice(5), // 只显示 MM-DD,避免 X 轴拥挤
    created: point.created,
    resolved: point.resolved,
  }));
  const oldestHoursLabel =
    data.oldest_open_age_hours == null
      ? "—"
      : data.oldest_open_age_hours >= 24
      ? `${(data.oldest_open_age_hours / 24).toFixed(1)} 天`
      : `${data.oldest_open_age_hours.toFixed(1)} 小时`;
  const slaBreachClass = data.sla_breach_total > 0 ? "text-destructive" : "";

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">工单看板</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            系统级排队、SLA 超时与最近 7 天进出趋势。SLA 阈值 {data.sla_hours} 小时。
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          disabled={isLoading}
          className="inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm hover:bg-accent disabled:opacity-50"
        >
          <RefreshCw className={cn("h-4 w-4", isLoading && "animate-spin")} />
          刷新
        </button>
      </div>

      {/* 顶部 4 张关键卡片:open / SLA 超时 / 最老 open / 已解决 */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={Inbox}
          label="未处理总数"
          value={data.open_total}
          hint={`pending ${data.pending_total} / processing ${data.processing_total}`}
        />
        <StatCard
          icon={AlertTriangle}
          label={`SLA 超时(>${data.sla_hours}h)`}
          value={data.sla_breach_total}
          valueClassName={slaBreachClass}
          hint="open 工单中已超阈值未关闭的条数"
        />
        <StatCard
          icon={Clock}
          label="最老未处理"
          value={oldestHoursLabel}
          hint="当前最久未关闭工单的创建时长"
        />
        <StatCard
          icon={TrendingUp}
          label="已解决"
          value={data.resolved_total}
          hint={`closed ${data.closed_total}`}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* 优先级分布:运营关心 urgent/high 是否堆积 */}
        <div className="rounded-lg border p-4">
          <h3 className="text-sm font-medium">未处理工单 — 按优先级</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            仅统计 pending + processing,反映当下排队压力。
          </p>
          {data.open_total > 0 ? (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={priorityData}>
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                  {priorityData.map((entry) => (
                    <Cell key={entry.name} fill={PRIORITY_COLORS[entry.name] ?? "#64748b"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="py-12 text-center text-sm text-muted-foreground">当前没有未处理工单</p>
          )}
        </div>

        {/* 7 天进出趋势:created vs resolved 一眼看出积压方向 */}
        <div className="rounded-lg border p-4">
          <h3 className="text-sm font-medium">7 天进出趋势</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            按天对比新建与已解决,持续 created &gt; resolved 即在积压。
          </p>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={trendData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} allowDecimals={false} />
              <Tooltip />
              <Legend />
              <Line
                type="monotone"
                dataKey="created"
                stroke="#f97316"
                strokeWidth={2}
                name="新建"
                dot={{ r: 3 }}
              />
              <Line
                type="monotone"
                dataKey="resolved"
                stroke="#22c55e"
                strokeWidth={2}
                name="已解决"
                dot={{ r: 3 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  hint,
  valueClassName,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number | string;
  hint?: string;
  valueClassName?: string;
}) {
  return (
    <div className="rounded-lg border p-4">
      <div className="flex items-start gap-3">
        <div className="rounded-md bg-primary/10 p-2">
          <Icon className="h-4 w-4 text-primary" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className={cn("mt-1 text-2xl font-bold", valueClassName)}>
            {typeof value === "number" ? value.toLocaleString() : value}
          </p>
          {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
        </div>
      </div>
    </div>
  );
}
