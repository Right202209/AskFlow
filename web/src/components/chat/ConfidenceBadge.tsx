import type { AnswerConfidence } from "@/types/chat";
import { cn } from "@/lib/utils";

const BAND_META: Record<
  AnswerConfidence["band"],
  { symbol: string; label: string; className: string }
> = {
  high: { symbol: "●", label: "高置信", className: "text-green-600 border-green-600/30 bg-green-600/10" },
  medium: { symbol: "◐", label: "中置信", className: "text-amber-600 border-amber-600/30 bg-amber-600/10" },
  low: { symbol: "○", label: "低置信", className: "text-red-600 border-red-600/30 bg-red-600/10" },
};

/** 回答置信度徽章（区别于意图置信度）；low 档追加转人工建议，未自检时如实标注。 */
export function ConfidenceBadge({ confidence }: { confidence: AnswerConfidence }) {
  const meta = BAND_META[confidence.band];
  const unverified = confidence.verify_pass_rate === null;

  return (
    <div
      className={cn(
        "inline-flex w-fit items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium",
        meta.className,
      )}
      title={`回答置信度 ${confidence.score.toFixed(2)}（检索 ${confidence.retrieval.toFixed(2)}${
        unverified ? "，未自检" : `，自检通过率 ${confidence.verify_pass_rate?.toFixed(2)}`
      }）`}
    >
      <span aria-hidden>{meta.symbol}</span>
      <span>
        {meta.label} ({confidence.score.toFixed(2)})
      </span>
      {unverified && <span className="opacity-70">· 未自检</span>}
      {confidence.band === "low" && <span className="opacity-80">· 建议核实或转人工</span>}
    </div>
  );
}
