import { useEffect, useState } from "react";
import { Loader2, RotateCcw } from "lucide-react";
import { toastError, toastSuccess } from "@/stores/toastStore";
import * as adminService from "@/services/admin";
import type { PromptTemplate, PromptVersion } from "@/types/prompt";

// 版本历史 + 回滚：激活历史版本只拨指针，不产生新行。
export function PromptVersionsDialog({
  prompt,
  isAdmin,
  onClose,
  onActivated,
}: {
  prompt: PromptTemplate;
  isAdmin: boolean;
  onClose: () => void;
  onActivated: () => void;
}) {
  const [versions, setVersions] = useState<PromptVersion[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [activatingVersion, setActivatingVersion] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const rows = await adminService.getPromptVersions(prompt.key);
        if (!cancelled) setVersions(rows);
      } catch (err) {
        const message = err instanceof Error ? err.message : "加载失败";
        toastError("加载版本历史失败", message);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [prompt.key]);

  const handleActivate = async (version: number) => {
    if (!window.confirm(`确定回滚「${prompt.key}」到 v${version}？该版本将立即生效。`)) return;
    setActivatingVersion(version);
    try {
      await adminService.activatePromptVersion(prompt.key, version);
      toastSuccess("已回滚", `v${version} 已生效`);
      onActivated();
    } catch (err) {
      const message = err instanceof Error ? err.message : "回滚失败";
      toastError("回滚失败", message);
    } finally {
      setActivatingVersion(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-lg border bg-card p-6 shadow-lg">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">
            版本历史「<code className="text-base">{prompt.key}</code>」
          </h2>
          <button onClick={onClose} className="rounded-md border px-3 py-1.5 text-sm hover:bg-accent">
            关闭
          </button>
        </div>

        {isLoading ? (
          <div className="flex justify-center py-16">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="mt-4 min-h-0 flex-1 space-y-3 overflow-auto">
            {versions.map((v) => {
              const isActive = v.version === prompt.active_version;
              return (
                <div key={v.id} className="rounded-lg border p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">v{v.version}</span>
                      {isActive && (
                        <span className="rounded bg-green-100 px-1.5 py-0.5 text-xs text-green-700">
                          当前生效
                        </span>
                      )}
                      <span className="text-xs text-muted-foreground">
                        {new Date(v.created_at).toLocaleString()}
                      </span>
                    </div>
                    {isAdmin && !isActive && (
                      <button
                        onClick={() => handleActivate(v.version)}
                        disabled={activatingVersion === v.version}
                        className="inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs hover:bg-accent disabled:opacity-50"
                      >
                        {activatingVersion === v.version ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <RotateCcw className="h-3 w-3" />
                        )}
                        回滚到此版本
                      </button>
                    )}
                  </div>
                  {v.comment && (
                    <p className="mt-1 text-xs text-muted-foreground">{v.comment}</p>
                  )}
                  <pre className="mt-2 max-h-28 overflow-auto whitespace-pre-wrap rounded bg-muted/50 p-2 text-xs text-muted-foreground">
                    {v.content}
                  </pre>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
