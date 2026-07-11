import type { Source } from "@/types/chat";

/** 引用点击后的原文展开卡片：展示完整 chunk 预览与出处信息。 */
export function SourceCard({ source }: { source: Source }) {
  return (
    <div className="rounded-md border bg-background p-2.5 text-left shadow-sm">
      <p className="flex items-center gap-1.5 text-xs font-medium">
        {source.index != null && (
          <span className="rounded bg-muted px-1 py-0.5 font-mono text-[10px]">
            [{source.index}]
          </span>
        )}
        <span className="truncate">{source.title || "未命名文档"}</span>
      </p>
      <p className="mt-1.5 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">
        {source.chunk}
      </p>
      <p className="mt-1.5 flex items-center gap-2 text-[10px] text-muted-foreground">
        <span>相关度 {(source.score * 100).toFixed(0)}%</span>
        {source.source && <span>来源：{source.source}</span>}
        {source.doc_id && <span className="truncate font-mono opacity-70">doc {source.doc_id}</span>}
      </p>
    </div>
  );
}
