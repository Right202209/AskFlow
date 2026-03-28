import type { Source } from "@/types/chat";

export function SourceCard({ source }: { source: Source }) {
  return (
    <div className="rounded-md border p-2">
      <p className="text-xs font-medium">{source.title}</p>
      <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
        {source.chunk}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        相关度 {(source.score * 100).toFixed(0)}%
      </p>
    </div>
  );
}
