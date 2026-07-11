import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Activity, AlertTriangle, CheckCircle2, Clock, Database } from "lucide-react";
import { getSystemHealth } from "@/services/admin";
import type { SystemHealthData } from "@/types/admin";
import { cn } from "@/lib/utils";

const DASHBOARD_REFRESH_MS = 30_000;

const DEP_LABELS: Record<string, string> = {
  postgres: "PostgreSQL",
  redis: "Redis",
  chroma: "ChromaDB",
  minio: "MinIO",
};

const DOC_STATUS_LABELS: Record<string, string> = {
  pending: "等待中",
  indexing: "索引中",
  active: "已索引",
  failed: "失败",
  archived: "已归档",
};

// 每 30s 拉一次系统健康，与 DashboardPage 现有拉取节奏一致；卸载时停轮询、丢弃在途结果。
function useSystemHealth() {
  const [data, setData] = useState<SystemHealthData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const next = await getSystemHealth();
        if (active) setData(next);
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : "加载系统健康失败");
      }
    };
    load();
    const timer = setInterval(load, DASHBOARD_REFRESH_MS);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  return { data, error };
}

function HealthHeader({
  status,
  appVersion,
  policyVersion,
}: {
  status: string;
  appVersion: string;
  policyVersion: string;
}) {
  const degraded = status !== "ok";
  return (
    <div className="flex items-center gap-2">
      <Activity className="h-4 w-4 text-primary" />
      <h3 className="text-sm font-medium">系统状态</h3>
      <span
        className={cn(
          "ml-2 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
          degraded ? "bg-red-100 text-red-800" : "bg-green-100 text-green-800",
        )}
      >
        {degraded ? <AlertTriangle className="h-3 w-3" /> : <CheckCircle2 className="h-3 w-3" />}
        {degraded ? "degraded" : "ok"}
      </span>
      <span className="ml-auto text-xs text-muted-foreground">
        v{appVersion} · {policyVersion}
      </span>
    </div>
  );
}

function DependencyGrid({ checks }: { checks: Record<string, string> }) {
  return (
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
      {Object.entries(checks).map(([name, state]) => {
        const ok = state === "ok";
        return (
          <div key={name} className="flex items-center gap-2 rounded-md border px-3 py-2">
            <span className={cn("h-2.5 w-2.5 rounded-full", ok ? "bg-green-500" : "bg-red-500")} />
            <span className="text-sm font-medium">{DEP_LABELS[name] ?? name}</span>
            <span className="ml-auto text-xs text-muted-foreground">{ok ? "正常" : state}</span>
          </div>
        );
      })}
    </div>
  );
}

function DocStatusTile({ status, count }: { status: string; count: number }) {
  const label = DOC_STATUS_LABELS[status] ?? status;
  const failed = status === "failed";
  const tile = (
    <div
      className={cn(
        "rounded-md border p-3 text-center",
        failed && count > 0 && "border-red-300 bg-red-50",
      )}
    >
      <p className="text-xl font-bold">{count}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
  // failed 磁贴深链到文档页并预置 failed 过滤，运营一键定位失败文档。
  return failed ? <Link to="/admin/documents?status=failed">{tile}</Link> : tile;
}

function DocStatusGrid({ byStatus }: { byStatus: Record<string, number> }) {
  return (
    <div>
      <p className="mb-2 text-xs font-medium text-muted-foreground">文档索引状态</p>
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
        {Object.entries(byStatus).map(([status, count]) => (
          <DocStatusTile key={status} status={status} count={count} />
        ))}
      </div>
    </div>
  );
}

function formatFreshness(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString() : "尚无已索引文档";
}

function FreshnessRow({ data }: { data: SystemHealthData }) {
  return (
    <div className="flex flex-wrap gap-4 text-sm">
      <div className="flex items-center gap-2">
        <Database className="h-4 w-4 text-muted-foreground" />
        <span>分块总数 {data.chunks_total.toLocaleString()}</span>
      </div>
      <div className="flex items-center gap-2">
        <Clock className="h-4 w-4 text-muted-foreground" />
        <span>最近索引 {formatFreshness(data.last_indexed_at)}</span>
      </div>
      {data.oldest_pending_age_hours != null && (
        <div className="flex items-center gap-2 text-yellow-700">
          <AlertTriangle className="h-4 w-4" />
          <span>最老等待 {data.oldest_pending_age_hours.toFixed(1)}h</span>
        </div>
      )}
    </div>
  );
}

export function SystemHealthPanel() {
  const { data, error } = useSystemHealth();

  if (error) {
    return (
      <div className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>
    );
  }
  if (!data) {
    return <p className="text-sm text-muted-foreground">加载系统健康…</p>;
  }

  return (
    <div className="space-y-4 rounded-lg border p-4">
      <HealthHeader
        status={data.status}
        appVersion={data.app_version}
        policyVersion={data.harness_policy_version}
      />
      <DependencyGrid checks={data.checks} />
      <DocStatusGrid byStatus={data.documents_by_status} />
      <FreshnessRow data={data} />
    </div>
  );
}
