import { useEffect, useRef, useState } from "react";
import { Loader2, Upload, RefreshCw, Trash2 } from "lucide-react";
import { useAdminStore } from "@/stores/adminStore";
import { useAuthStore } from "@/stores/authStore";
import { toastError, toastSuccess } from "@/stores/toastStore";
import * as documentService from "@/services/document";
import { cn } from "@/lib/utils";
import type { DocumentStatus } from "@/types/document";

const STATUS_LABELS: Record<DocumentStatus, string> = {
  pending: "等待中",
  processing: "处理中",
  indexed: "已索引",
  failed: "失败",
};

const STATUS_COLORS: Record<DocumentStatus, string> = {
  pending: "bg-yellow-100 text-yellow-800",
  processing: "bg-blue-100 text-blue-800",
  indexed: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
};

export function DocumentsPage() {
  const { documents, isLoading, error, fetchDocuments } = useAdminStore();
  const role = useAuthStore((s) => s.role);
  const isAdmin = role === "admin";
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const [statusFilter, setStatusFilter] = useState<DocumentStatus | "all">("all");

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("title", file.name);
      await documentService.uploadDocument(formData);
      await fetchDocuments();
      toastSuccess("文档上传成功", file.name);
    } catch (error) {
      toastError(
        "上传失败",
        error instanceof Error ? error.message : "上传文档时发生错误",
      );
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handleReindex = async (id: string) => {
    try {
      await documentService.reindexDocument(id);
      await fetchDocuments();
      toastSuccess("已触发重建索引");
    } catch (error) {
      toastError(
        "重建索引失败",
        error instanceof Error ? error.message : "重建索引时发生错误",
      );
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确定删除该文档？")) return;
    try {
      await documentService.deleteDocument(id);
      await fetchDocuments();
      toastSuccess("文档已删除");
    } catch (error) {
      toastError(
        "删除失败",
        error instanceof Error ? error.message : "删除文档时发生错误",
      );
    }
  };

  const filtered = statusFilter === "all"
    ? documents
    : documents.filter((d) => d.status === statusFilter);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">文档管理</h1>
        <div>
          <input
            ref={fileRef}
            type="file"
            onChange={handleUpload}
            className="hidden"
            accept=".pdf,.docx,.md,.html,.txt"
          />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow hover:bg-primary/90 disabled:opacity-50"
          >
            <Upload className="h-4 w-4" />
            {uploading ? "上传中..." : "上传文档"}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Status filter */}
      <div className="flex gap-1">
        {(["all", "pending", "processing", "indexed", "failed"] as const).map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={cn(
              "rounded-md px-3 py-1.5 text-sm transition-colors",
              statusFilter === s
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-accent",
            )}
          >
            {s === "all" ? "全部" : STATUS_LABELS[s]}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex justify-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : filtered.length === 0 ? (
        <p className="py-20 text-center text-sm text-muted-foreground">暂无文档</p>
      ) : (
        <div className="overflow-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="px-4 py-3 text-left font-medium">标题</th>
                <th className="px-4 py-3 text-left font-medium">文件名</th>
                <th className="px-4 py-3 text-left font-medium">状态</th>
                <th className="px-4 py-3 text-left font-medium">分块数</th>
                <th className="px-4 py-3 text-left font-medium">创建时间</th>
                {isAdmin && <th className="px-4 py-3 text-left font-medium">操作</th>}
              </tr>
            </thead>
            <tbody>
              {filtered.map((doc) => (
                <tr key={doc.id} className="border-b transition-colors hover:bg-muted/50">
                  <td className="px-4 py-3 font-medium">{doc.title}</td>
                  <td className="px-4 py-3 text-muted-foreground">{doc.filename}</td>
                  <td className="px-4 py-3">
                    <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", STATUS_COLORS[doc.status])}>
                      {STATUS_LABELS[doc.status]}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{doc.chunk_count}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(doc.created_at).toLocaleDateString()}
                  </td>
                  {isAdmin && (
                    <td className="px-4 py-3">
                      <div className="flex gap-1">
                        <button
                          onClick={() => handleReindex(doc.id)}
                          className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
                          title="重建索引"
                        >
                          <RefreshCw className="h-3.5 w-3.5" />
                        </button>
                        <button
                          onClick={() => handleDelete(doc.id)}
                          className="rounded p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                          title="删除"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
