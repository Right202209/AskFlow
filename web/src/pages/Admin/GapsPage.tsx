import { useEffect, useState } from "react";
import { Link } from "react-router";
import { FilePlus2, Loader2, RefreshCw, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { DraftSourceDialog } from "@/components/admin/DraftSourceDialog";
import * as adminService from "@/services/admin";
import type { GapStatus, KnowledgeGap } from "@/types/knowledge";

const STATUS_FILTERS: Array<{ label: string; value: GapStatus }> = [
  { label: "待处理", value: "open" },
  { label: "已转知识", value: "promoted" },
  { label: "已忽略", value: "dismissed" },
];

// 五类失败信号的中文标签与配色，与后端 gap_recorder.GAP_SIGNAL_KINDS 对齐。
const SIGNAL_META: Record<string, { label: string; className: string }> = {
  clarify: { label: "追问澄清", className: "bg-amber-100 text-amber-800" },
  rag_refusal: { label: "检索拒答", className: "bg-red-100 text-red-800" },
  low_retrieval_score: { label: "弱检索", className: "bg-orange-100 text-orange-800" },
  handoff: { label: "转人工", className: "bg-purple-100 text-purple-800" },
  negative_feedback: { label: "差评", className: "bg-rose-100 text-rose-800" },
};

const PAGE_SIZE = 20;

function SignalChips({ signals }: { signals: Record<string, number> }) {
  const entries = Object.entries(signals).filter(([, count]) => count > 0);
  if (entries.length === 0) {
    return <span className="text-xs text-muted-foreground">—</span>;
  }
  return (
    <div className="flex flex-wrap gap-1">
      {entries.map(([kind, count]) => {
        const meta = SIGNAL_META[kind] ?? {
          label: kind,
          className: "bg-gray-100 text-gray-700",
        };
        return (
          <span
            key={kind}
            className={cn("rounded-full px-2 py-0.5 text-xs font-medium", meta.className)}
          >
            {meta.label} {count}
          </span>
        );
      })}
    </div>
  );
}

export function GapsPage() {
  const [gaps, setGaps] = useState<KnowledgeGap[]>([]);
  const [statusFilter, setStatusFilter] = useState<GapStatus>("open");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dismissing, setDismissing] = useState<string | null>(null);
  const [draftingGap, setDraftingGap] = useState<KnowledgeGap | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadGaps = async (status: GapStatus) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await adminService.getKnowledgeGaps(status, PAGE_SIZE, 0);
      setGaps(data);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "加载知识缺口失败");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadGaps(statusFilter);
  }, [statusFilter]);

  const handleDismiss = async (id: string) => {
    setDismissing(id);
    try {
      await adminService.dismissKnowledgeGap(id);
      setGaps((prev) => prev.filter((gap) => gap.id !== id));
    } catch (dismissError) {
      setError(dismissError instanceof Error ? dismissError.message : "忽略缺口失败");
    } finally {
      setDismissing(null);
    }
  };

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">知识缺口</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            机器人没答上来的问题，按出现频次排序——优先补齐这些知识。
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadGaps(statusFilter)}
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
      {notice && (
        <div className="rounded-md bg-green-500/10 px-4 py-3 text-sm text-green-700">
          {notice}
        </div>
      )}

      {isLoading ? (
        <div className="flex justify-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : gaps.length === 0 ? (
        <p className="py-20 text-center text-sm text-muted-foreground">暂无知识缺口</p>
      ) : (
        <div className="overflow-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="px-4 py-3 text-left font-medium">问题</th>
                <th className="px-4 py-3 text-left font-medium">频次</th>
                <th className="px-4 py-3 text-left font-medium">信号</th>
                <th className="px-4 py-3 text-left font-medium">意图</th>
                <th className="px-4 py-3 text-left font-medium">更新时间</th>
                <th className="px-4 py-3 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {gaps.map((gap) => (
                <tr key={gap.id} className="border-b transition-colors hover:bg-muted/50">
                  <td className="max-w-md px-4 py-3">
                    {gap.example_conversation_id ? (
                      <Link
                        to={`/app/chat/${gap.example_conversation_id}`}
                        className="font-medium text-primary hover:underline"
                      >
                        {gap.question}
                      </Link>
                    ) : (
                      <span className="font-medium">{gap.question}</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-semibold text-primary">
                      {gap.frequency}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <SignalChips signals={gap.signals} />
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{gap.last_intent || "—"}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(gap.updated_at).toLocaleString("zh-CN")}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {gap.status === "open" && (
                      <div className="flex justify-end gap-1.5">
                        <button
                          type="button"
                          onClick={() => setDraftingGap(gap)}
                          className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs text-primary hover:bg-primary/10"
                        >
                          <FilePlus2 className="h-3 w-3" />
                          草拟
                        </button>
                        <button
                          type="button"
                          onClick={() => void handleDismiss(gap.id)}
                          disabled={dismissing === gap.id}
                          className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs text-muted-foreground hover:bg-accent disabled:opacity-50"
                        >
                          {dismissing === gap.id ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : (
                            <X className="h-3 w-3" />
                          )}
                          忽略
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {draftingGap && (
        <DraftSourceDialog
          gap={draftingGap}
          onClose={() => setDraftingGap(null)}
          onCreated={() => {
            setDraftingGap(null);
            setNotice("草稿已创建，请到「知识条目评审」页面继续评审发布。");
          }}
        />
      )}
    </div>
  );
}
