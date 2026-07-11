import { useEffect, useState } from "react";
import { Check, Loader2, RefreshCw, Save, X } from "lucide-react";
import { cn } from "@/lib/utils";
import * as adminService from "@/services/admin";
import { useAuthStore } from "@/stores/authStore";
import type { DraftStatus, KnowledgeDraft } from "@/types/knowledge";

const STATUS_FILTERS: Array<{ label: string; value: DraftStatus }> = [
  { label: "待评审", value: "draft" },
  { label: "已发布", value: "approved" },
  { label: "已驳回", value: "rejected" },
];

const PAGE_SIZE = 20;

export function KnowledgePage() {
  const role = useAuthStore((s) => s.role);
  const isAdmin = role === "admin";

  const [drafts, setDrafts] = useState<KnowledgeDraft[]>([]);
  const [statusFilter, setStatusFilter] = useState<DraftStatus>("draft");
  const [selected, setSelected] = useState<KnowledgeDraft | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadDrafts = async (status: DraftStatus) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await adminService.getKnowledgeDrafts(status, PAGE_SIZE, 0);
      setDrafts(data);
      setSelected(null);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "加载草稿失败");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadDrafts(statusFilter);
  }, [statusFilter]);

  const selectDraft = (draft: KnowledgeDraft) => {
    setSelected(draft);
    setQuestion(draft.question);
    setAnswer(draft.answer);
    setNotice(null);
    setError(null);
  };

  const runAction = async (action: () => Promise<string>) => {
    if (!selected) return;
    setIsBusy(true);
    setError(null);
    setNotice(null);
    try {
      setNotice(await action());
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "操作失败");
    } finally {
      setIsBusy(false);
    }
  };

  const handleSave = () =>
    runAction(async () => {
      const updated = await adminService.updateKnowledgeDraft(selected!.id, {
        question,
        answer,
      });
      setDrafts((prev) => prev.map((d) => (d.id === updated.id ? updated : d)));
      setSelected(updated);
      return "草稿已保存";
    });

  const handleApprove = () =>
    runAction(async () => {
      const doc = await adminService.approveKnowledgeDraft(selected!.id);
      setDrafts((prev) => prev.filter((d) => d.id !== selected!.id));
      setSelected(null);
      return `已发布为文档「${doc.title}」，可在文档管理中查看`;
    });

  const handleReject = () =>
    runAction(async () => {
      const note = window.prompt("驳回原因（可选）：") ?? undefined;
      await adminService.rejectKnowledgeDraft(selected!.id, note);
      setDrafts((prev) => prev.filter((d) => d.id !== selected!.id));
      setSelected(null);
      return "草稿已驳回，对应缺口保持待处理";
    });

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">知识条目评审</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            评审由缺口草拟的知识条目；通过后自动发布进知识库（文档管线）。
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadDrafts(statusFilter)}
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
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(280px,1fr)_2fr]">
          <div className="overflow-auto rounded-lg border">
            {drafts.length === 0 ? (
              <p className="py-16 text-center text-sm text-muted-foreground">暂无草稿</p>
            ) : (
              <ul className="divide-y">
                {drafts.map((draft) => (
                  <li key={draft.id}>
                    <button
                      type="button"
                      onClick={() => selectDraft(draft)}
                      className={cn(
                        "w-full px-4 py-3 text-left transition-colors hover:bg-muted/50",
                        selected?.id === draft.id && "bg-muted",
                      )}
                    >
                      <p className="line-clamp-2 text-sm font-medium">{draft.question}</p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {draft.synthesis?.generated ? "AI 草拟" : "人工/素材"} ·{" "}
                        {new Date(draft.updated_at).toLocaleString("zh-CN")}
                      </p>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="rounded-lg border p-4">
            {!selected ? (
              <p className="py-16 text-center text-sm text-muted-foreground">
                从左侧选择一条草稿开始评审
              </p>
            ) : (
              <div className="space-y-4">
                <div>
                  <label className="text-xs font-medium text-muted-foreground">问题</label>
                  <input
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    disabled={selected.status !== "draft"}
                    className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm disabled:opacity-60"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground">
                    答案（markdown）
                  </label>
                  <textarea
                    value={answer}
                    onChange={(e) => setAnswer(e.target.value)}
                    disabled={selected.status !== "draft"}
                    rows={14}
                    className="mt-1 w-full rounded-md border bg-background px-3 py-2 font-mono text-sm disabled:opacity-60"
                  />
                </div>
                <div className="text-xs text-muted-foreground">
                  {selected.source_ticket_id && <p>素材工单：{selected.source_ticket_id}</p>}
                  {selected.source_conversation_id && (
                    <p>素材会话：{selected.source_conversation_id}</p>
                  )}
                  {selected.review_note && <p>评审备注:{selected.review_note}</p>}
                </div>

                {selected.status === "draft" && (
                  <div className="flex items-center gap-2 border-t pt-4">
                    <button
                      type="button"
                      onClick={() => void handleSave()}
                      disabled={isBusy}
                      className="inline-flex items-center gap-1.5 rounded-md border px-3 py-2 text-sm hover:bg-accent disabled:opacity-50"
                    >
                      <Save className="h-4 w-4" /> 保存
                    </button>
                    {isAdmin && (
                      <>
                        <button
                          type="button"
                          onClick={() => void handleApprove()}
                          disabled={isBusy}
                          className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                        >
                          <Check className="h-4 w-4" /> 通过并发布
                        </button>
                        <button
                          type="button"
                          onClick={() => void handleReject()}
                          disabled={isBusy}
                          className="inline-flex items-center gap-1.5 rounded-md border border-destructive/40 px-3 py-2 text-sm text-destructive hover:bg-destructive/10 disabled:opacity-50"
                        >
                          <X className="h-4 w-4" /> 驳回
                        </button>
                      </>
                    )}
                    {isBusy && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
