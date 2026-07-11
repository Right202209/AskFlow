import { useState } from "react";
import { toastError, toastSuccess } from "@/stores/toastStore";
import * as adminService from "@/services/admin";
import type { PromptTemplate } from "@/types/prompt";

// 编辑 = 追加新版本并激活；占位符错拼由服务端二次校验（422）兜底。
export function PromptEditDialog({
  prompt,
  hint,
  onClose,
  onSaved,
}: {
  prompt: PromptTemplate;
  hint?: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [content, setContent] = useState(prompt.content ?? "");
  const [comment, setComment] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      await adminService.updatePrompt(prompt.key, {
        content,
        comment: comment || null,
      });
      toastSuccess("提示词已更新", "新版本已生效");
      onSaved();
    } catch (err) {
      const message = err instanceof Error ? err.message : "保存失败";
      setError(message);
      toastError("保存失败", message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-lg border bg-card p-6 shadow-lg">
        <h2 className="text-lg font-semibold">
          编辑「<code className="text-base">{prompt.key}</code>」
        </h2>

        {prompt.variables.length > 0 && (
          <p className="mt-1 text-xs text-muted-foreground">
            可用占位符：{prompt.variables.map((v) => `{${v}}`).join(", ")}
          </p>
        )}
        {hint && (
          <p className="mt-2 rounded bg-amber-50 px-2 py-1 text-xs text-amber-700">{hint}</p>
        )}

        {error && (
          <div className="mt-3 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-4 flex min-h-0 flex-1 flex-col space-y-3">
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            required
            rows={12}
            className="min-h-0 flex-1 resize-none rounded-md border bg-transparent p-3 font-mono text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          />
          <div className="space-y-1">
            <label className="text-sm font-medium">变更说明（可选）</label>
            <input
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="记录本次修改原因，便于回滚时对照"
              className="flex h-9 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
          </div>

          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border px-4 py-2 text-sm hover:bg-accent"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={saving}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow hover:bg-primary/90 disabled:opacity-50"
            >
              {saving ? "保存中..." : "保存并生效"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
