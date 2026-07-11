import { useEffect, useState } from "react";
import { Loader2, Pencil, History } from "lucide-react";
import { useAuthStore } from "@/stores/authStore";
import { toastError } from "@/stores/toastStore";
import * as adminService from "@/services/admin";
import type { PromptTemplate } from "@/types/prompt";
import { PromptEditDialog } from "./PromptEditDialog";
import { PromptVersionsDialog } from "./PromptVersionsDialog";

// 每个 key 的编辑警示——服务端也会二次校验，这里先给客服/管理员一个显式提醒。
const PROMPT_HINTS: Record<string, string> = {
  "intent.classifier":
    "分类器提示词必须保留 {message} 占位符，且六个意图标签不可删改，否则路由会错乱。",
  "rag.fallback_llm_down":
    "前端按该文案前缀识别「降级渲染」，改动前缀会影响用户端展示，请谨慎。",
};

export function PromptsPage() {
  const role = useAuthStore((s) => s.role);
  const isAdmin = role === "admin";
  const [prompts, setPrompts] = useState<PromptTemplate[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<PromptTemplate | null>(null);
  const [viewingVersions, setViewingVersions] = useState<PromptTemplate | null>(null);

  const load = async () => {
    setIsLoading(true);
    setError("");
    try {
      setPrompts(await adminService.getPrompts());
    } catch (err) {
      const message = err instanceof Error ? err.message : "加载失败";
      setError(message);
      toastError("加载失败", message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-xl font-semibold">提示词模板</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          编辑追加新版本并立即生效；历史版本只增不改，可随时回滚。
          {!isAdmin && " 当前角色仅可查看，编辑与回滚需管理员权限。"}
        </p>
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
      ) : prompts.length === 0 ? (
        <p className="py-20 text-center text-sm text-muted-foreground">暂无提示词模板</p>
      ) : (
        <div className="space-y-3">
          {prompts.map((prompt) => (
            <PromptCard
              key={prompt.key}
              prompt={prompt}
              hint={PROMPT_HINTS[prompt.key]}
              isAdmin={isAdmin}
              onEdit={() => setEditing(prompt)}
              onHistory={() => setViewingVersions(prompt)}
            />
          ))}
        </div>
      )}

      {editing && (
        <PromptEditDialog
          prompt={editing}
          hint={PROMPT_HINTS[editing.key]}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            void load();
          }}
        />
      )}

      {viewingVersions && (
        <PromptVersionsDialog
          prompt={viewingVersions}
          isAdmin={isAdmin}
          onClose={() => setViewingVersions(null)}
          onActivated={() => {
            setViewingVersions(null);
            void load();
          }}
        />
      )}
    </div>
  );
}

function PromptCard({
  prompt,
  hint,
  isAdmin,
  onEdit,
  onHistory,
}: {
  prompt: PromptTemplate;
  hint?: string;
  isAdmin: boolean;
  onEdit: () => void;
  onHistory: () => void;
}) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <code className="rounded bg-muted px-1.5 py-0.5 text-sm font-medium">{prompt.key}</code>
            {prompt.active_version != null && (
              <span className="text-xs text-muted-foreground">v{prompt.active_version}</span>
            )}
          </div>
          {prompt.description && (
            <p className="mt-1 text-sm text-muted-foreground">{prompt.description}</p>
          )}
          {prompt.variables.length > 0 && (
            <p className="mt-1 text-xs text-muted-foreground">
              占位符：{prompt.variables.map((v) => `{${v}}`).join(", ")}
            </p>
          )}
          {hint && (
            <p className="mt-2 rounded bg-amber-50 px-2 py-1 text-xs text-amber-700">{hint}</p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button
            onClick={onHistory}
            className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
            title="版本历史"
          >
            <History className="h-4 w-4" />
          </button>
          {isAdmin && (
            <button
              onClick={onEdit}
              className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
              title="编辑"
            >
              <Pencil className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>
      {prompt.content && (
        <pre className="mt-3 max-h-32 overflow-auto whitespace-pre-wrap rounded bg-muted/50 p-3 text-xs text-muted-foreground">
          {prompt.content}
        </pre>
      )}
    </div>
  );
}
