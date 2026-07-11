import type { ReactNode } from "react";

// 与后端 rag/verifier.py 的 CITATION_MARKER_RE 保持一致。
export const CITATION_MARKER_SOURCE = "\\[(\\d{1,2})\\]";

interface CitationChipProps {
  n: number;
  active?: boolean;
  onClick?: (n: number) => void;
}

export function CitationChip({ n, active = false, onClick }: CitationChipProps) {
  return (
    <button
      type="button"
      aria-label={`查看引用来源 ${n}`}
      onClick={() => onClick?.(n)}
      className={
        "mx-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded px-1 align-text-top " +
        "font-mono text-[10px] leading-none transition-colors " +
        (active
          ? "bg-primary text-primary-foreground"
          : "bg-background/70 text-muted-foreground hover:bg-primary/20 hover:text-foreground")
      }
    >
      {n}
    </button>
  );
}

/**
 * 把回答文本按 [n] 引用标记切分成 文本 + CitationChip 节点。
 * 越界编号（无对应来源）按普通文本渲染；流式中途的 "[​" / "[1" 不匹配正则，
 * 自然保持为普通文本——无需任何闪烁启发式。
 */
export function renderWithCitations(
  content: string,
  sourceCount: number,
  options?: {
    activeIndex?: number | null;
    onCitationClick?: (n: number) => void;
  },
): ReactNode[] {
  const nodes: ReactNode[] = [];
  const re = new RegExp(CITATION_MARKER_SOURCE, "g");
  let last = 0;
  let key = 0;
  let match: RegExpExecArray | null;

  while ((match = re.exec(content)) !== null) {
    if (match.index > last) {
      nodes.push(content.slice(last, match.index));
    }
    const n = Number.parseInt(match[1] ?? "0", 10);
    if (n >= 1 && n <= sourceCount) {
      nodes.push(
        <CitationChip
          key={`citation-${key++}`}
          n={n}
          active={options?.activeIndex === n}
          onClick={options?.onCitationClick}
        />,
      );
    } else {
      // 越界标记：不可点击、不改写文本（后端把它记为 invalid_citations）。
      nodes.push(match[0]);
    }
    last = match.index + match[0].length;
  }
  if (last < content.length) {
    nodes.push(content.slice(last));
  }
  return nodes;
}
