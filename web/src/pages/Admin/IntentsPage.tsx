import { useEffect, useState } from "react";
import { Loader2, Plus, Pencil } from "lucide-react";
import { useAdminStore } from "@/stores/adminStore";
import { useAuthStore } from "@/stores/authStore";
import { toastError, toastSuccess } from "@/stores/toastStore";
import * as adminService from "@/services/admin";
import type { IntentConfig, CreateIntentRequest, UpdateIntentRequest } from "@/types/intent";

export function IntentsPage() {
  const { intents, isLoading, error, fetchIntents } = useAdminStore();
  const role = useAuthStore((s) => s.role);
  const isAdmin = role === "admin";
  const [editingIntent, setEditingIntent] = useState<IntentConfig | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  useEffect(() => {
    fetchIntents();
  }, [fetchIntents]);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">意图配置</h1>
        {isAdmin && (
          <button
            onClick={() => setIsCreating(true)}
            className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow hover:bg-primary/90"
          >
            <Plus className="h-4 w-4" />
            新建意图
          </button>
        )}
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
      ) : intents.length === 0 ? (
        <p className="py-20 text-center text-sm text-muted-foreground">暂无意图配置</p>
      ) : (
        <div className="overflow-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="px-4 py-3 text-left font-medium">名称</th>
                <th className="px-4 py-3 text-left font-medium">显示名</th>
                <th className="px-4 py-3 text-left font-medium">路由目标</th>
                <th className="px-4 py-3 text-left font-medium">阈值</th>
                <th className="px-4 py-3 text-left font-medium">优先级</th>
                {isAdmin && <th className="px-4 py-3 text-left font-medium">操作</th>}
              </tr>
            </thead>
            <tbody>
              {intents.map((intent) => (
                <tr key={intent.id} className="border-b transition-colors hover:bg-muted/50">
                  <td className="px-4 py-3 font-medium">{intent.name}</td>
                  <td className="px-4 py-3">{intent.display_name}</td>
                  <td className="px-4 py-3 text-muted-foreground">{intent.route_target}</td>
                  <td className="px-4 py-3 text-muted-foreground">{intent.confidence_threshold}</td>
                  <td className="px-4 py-3 text-muted-foreground">{intent.priority}</td>
                  {isAdmin && (
                    <td className="px-4 py-3">
                      <button
                        onClick={() => setEditingIntent(intent)}
                        className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
                        title="编辑"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create/Edit Dialog */}
      {(isCreating || editingIntent) && (
        <IntentFormDialog
          intent={editingIntent}
          onClose={() => {
            setIsCreating(false);
            setEditingIntent(null);
          }}
          onSaved={() => {
            setIsCreating(false);
            setEditingIntent(null);
            fetchIntents();
          }}
        />
      )}
    </div>
  );
}

function IntentFormDialog({
  intent,
  onClose,
  onSaved,
}: {
  intent: IntentConfig | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isEditing = !!intent;
  const [name, setName] = useState(intent?.name ?? "");
  const [displayName, setDisplayName] = useState(intent?.display_name ?? "");
  const [description, setDescription] = useState(intent?.description ?? "");
  const [routeTarget, setRouteTarget] = useState(intent?.route_target ?? "rag");
  const [threshold, setThreshold] = useState(String(intent?.confidence_threshold ?? 0.7));
  const [priority, setPriority] = useState(String(intent?.priority ?? 0));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      if (isEditing && intent) {
        const data: UpdateIntentRequest = {
          display_name: displayName,
          description: description || undefined,
          route_target: routeTarget,
          confidence_threshold: parseFloat(threshold),
          priority: parseInt(priority, 10),
        };
        await adminService.updateIntent(intent.id, data);
      } else {
        const data: CreateIntentRequest = {
          name,
          display_name: displayName,
          description: description || undefined,
          route_target: routeTarget,
          confidence_threshold: parseFloat(threshold),
          priority: parseInt(priority, 10),
        };
        await adminService.createIntent(data);
      }
      toastSuccess(isEditing ? "意图已更新" : "意图已创建");
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-md rounded-lg border bg-card p-6 shadow-lg">
        <h2 className="text-lg font-semibold">{isEditing ? "编辑意图" : "新建意图"}</h2>

        {error && (
          <div className="mt-3 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-4 space-y-3">
          {!isEditing && (
            <Field label="名称" value={name} onChange={setName} required />
          )}
          <Field label="显示名" value={displayName} onChange={setDisplayName} required />
          <Field label="描述" value={description} onChange={setDescription} />
          <Field label="路由目标" value={routeTarget} onChange={setRouteTarget} required />
          <Field label="置信度阈值" value={threshold} onChange={setThreshold} type="number" />
          <Field label="优先级" value={priority} onChange={setPriority} type="number" />

          <div className="flex justify-end gap-2 pt-2">
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
              {saving ? "保存中..." : "保存"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  required,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  required?: boolean;
  type?: string;
}) {
  return (
    <div className="space-y-1">
      <label className="text-sm font-medium">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        step={type === "number" ? "0.01" : undefined}
        className="flex h-9 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      />
    </div>
  );
}
