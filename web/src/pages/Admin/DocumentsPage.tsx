import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Loader2, Upload, RefreshCw, RotateCcw, Trash2 } from "lucide-react";
import { useAdminStore } from "@/stores/adminStore";
import { useAuthStore } from "@/stores/authStore";
import { toastError, toastSuccess } from "@/stores/toastStore";
import * as documentService from "@/services/document";
import { cn } from "@/lib/utils";
import type { Document, DocumentStatus } from "@/types/document";

const STATUS_LABELS: Record<DocumentStatus, string> = {
  pending: "等待中",
  indexing: "索引中",
  active: "已索引",
  failed: "失败",
  archived: "已归档",
};

const STATUS_COLORS: Record<DocumentStatus, string> = {
  pending: "bg-yellow-100 text-yellow-800",
  indexing: "bg-blue-100 text-blue-800",
  active: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
  archived: "bg-gray-100 text-gray-600",
};

const FILTER_OPTIONS = ["all", "pending", "indexing", "active", "failed", "archived"] as const;

const POLL_INTERVAL_MS = 3000;
const POLL_MAX_MINUTES = 30;
const POLL_MAX_MS = POLL_MAX_MINUTES * 60 * 1000;

const isInFlight = (doc: Document) => doc.status === "pending" || doc.status === "indexing";

function StatusBadge({ doc }: { doc: Document }) {
  return (
    <span
      className={cn("rounded-full px-2 py-0.5 text-xs font-medium", STATUS_COLORS[doc.status])}
      title={doc.status === "failed" && doc.index_error ? doc.index_error : undefined}
    >
      {STATUS_LABELS[doc.status]}
      {isInFlight(doc) && <Loader2 className="ml-1 inline h-3 w-3 animate-spin" />}
    </span>
  );
}

function usePollWhileIndexing(documents: Document[], refresh: () => Promise<void>) {
  const pollStartRef = useRef<number | null>(null);
  const hasInFlight = documents.some(isInFlight);

  useEffect(() => {
    if (!hasInFlight) {
      pollStartRef.current = null;
      return;
    }
    if (pollStartRef.current === null) pollStartRef.current = Date.now();
    if (Date.now() - pollStartRef.current > POLL_MAX_MS) return;
    const timer = setTimeout(() => refresh(), POLL_INTERVAL_MS);
    return () => clearTimeout(timer);
  }, [documents, hasInFlight, refresh]);
}

export function DocumentsPage() {
  const { documents, isLoading, error, fetchDocuments } = useAdminStore();
  const role = useAuthStore((s) => s.role);
  const isAdmin = role === "admin";
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  // System 面板的 failed 磁贴通过 ?status=failed 深链过来——初始过滤取自 URL，非法值回落 all。
  const [searchParams] = useSearchParams();
  const urlStatus = searchParams.get("status");
  const initialFilter: DocumentStatus | "all" =
    urlStatus && (FILTER_OPTIONS as readonly string[]).includes(urlStatus)
      ? (urlStatus as DocumentStatus | "all")
      : "all";
  const [statusFilter, setStatusFilter] = useState<DocumentStatus | "all">(initialFilter);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  usePollWhileIndexing(documents, fetchDocuments);

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
      toastSuccess("文档已上传，正在后台索引", file.name);
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

  const handleReindex = async (id: string, isRetry = false) => {
    try {
      await documentService.reindexDocument(id);
      await fetchDocuments();
      toastSuccess(isRetry ? "已重新排队索引" : "已触发重建索引");
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
        {FILTER_OPTIONS.map((s) => (
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

      {isLoading && documents.length === 0 ? (
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
                  <td className="px-4 py-3 text-muted-foreground">{doc.file_path}</td>
                  <td className="px-4 py-3">
                    <StatusBadge doc={doc} />
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{doc.chunk_count}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(doc.created_at).toLocaleDateString()}
                  </td>
                  {isAdmin && (
                    <td className="px-4 py-3">
                      <div className="flex gap-1">
                        {doc.status === "failed" ? (
                          <button
                            onClick={() => handleReindex(doc.id, true)}
                            className="inline-flex items-center gap-1 rounded px-1.5 py-1 text-xs text-red-700 hover:bg-red-50"
                            title={doc.index_error ?? "重试索引"}
                          >
                            <RotateCcw className="h-3.5 w-3.5" />
                            重试
                          </button>
                        ) : (
                          <button
                            onClick={() => handleReindex(doc.id)}
                            disabled={isInFlight(doc)}
                            className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-40"
                            title="重建索引"
                          >
                            <RefreshCw className="h-3.5 w-3.5" />
                          </button>
                        )}
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
