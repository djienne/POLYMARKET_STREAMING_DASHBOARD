import { useDash } from "../lib/store";
import { fmtProb, fmtRatio } from "../lib/format";
import type { EdgeRatio, WindowZone } from "../lib/types";

export default function EdgeRatioPanel() {
  const edgeUp = useDash((s) => s.edgeUp);
  const edgeDown = useDash((s) => s.edgeDown);
  const window = useDash((s) => s.window);
  const zone: WindowZone = window?.zone ?? "unknown";
  const blocked = zone === "blocked_first" || zone === "blocked_last";

  return (
    <div className="card px-3 pt-2 pb-1.5 self-start flex flex-col justify-start overflow-hidden">
      <div className="flex items-baseline justify-between mb-1">
        <h2 className="card-header">Edge Ratio</h2>
        {blocked && (
          <span className="chip chip-warn text-[8px] px-1.5 py-0 font-mono leading-tight">
            blocked
          </span>
        )}
      </div>
      <div className="grid grid-cols-1 gap-1 content-start auto-rows-min">
        <EdgeRow edge={edgeUp} blocked={blocked} />
        <EdgeRow edge={edgeDown} blocked={blocked} />
      </div>
    </div>
  );
}

function EdgeRow({
  edge,
  blocked,
}: {
  edge: EdgeRatio | null;
  blocked: boolean;
}) {
  if (!edge) {
    return (
      <div className="border border-ink-800 rounded-lg px-2 py-1.5 text-slate-500 text-xs">
        Waiting for probabilities...
      </div>
    );
  }

  const hasEdge = edge.has_edge === true;
  const sideColor = edge.side === "UP" ? "text-emerald-300" : "text-rose-300";

  const max = Math.max(edge.current_ratio ?? 0, edge.required_ratio ?? 0, 1.5);
  const curW =
    edge.current_ratio != null ? (edge.current_ratio / max) * 100 : 0;
  const reqW =
    edge.required_ratio != null ? (edge.required_ratio / max) * 100 : 0;

  let chipClass: string;
  let chipText: string;
  if (blocked) {
    chipClass = "chip-warn";
    chipText = hasEdge ? "edge+hold" : "hold";
  } else if (edge.has_edge == null) {
    chipClass = "chip-mute";
    chipText = "--";
  } else if (hasEdge) {
    chipClass = "chip-up";
    chipText = "edge";
  } else {
    chipClass = "chip-down";
    chipText = "none";
  }

  const barColor = blocked
    ? "bg-amber-500/50"
    : hasEdge
      ? "bg-emerald-500/60"
      : "bg-rose-500/50";

  const probLine = `m ${fmtProb(edge.model_prob)}  p ${fmtProb(edge.market_prob)}  r ${fmtProb(edge.required_prob)}`;

  return (
    <div className="rounded-lg border border-ink-800 bg-ink-900/40 px-2 py-1.5">
      <div className="flex items-center justify-between mb-0.5">
        <div className="flex items-baseline gap-1.5">
          <span className={`font-semibold tracking-wide ${sideColor}`}>
            {edge.side}
          </span>
          <span className="text-[8px] uppercase tracking-widest text-slate-500">
            ratios + probs
          </span>
        </div>
        <span className={`chip ${chipClass} text-[8px] px-1.5 py-0 font-mono leading-tight`}>
          {chipText}
        </span>
      </div>

      <div className="flex items-baseline justify-between gap-2 mb-0.5 font-mono">
        <InlineMetric
          label="cur r"
          value={fmtRatio(edge.current_ratio)}
          hi
          positive={hasEdge}
        />
        <InlineMetric label="req r" value={fmtRatio(edge.required_ratio)} />
        <InlineMetric
          label="dr"
          value={
            edge.margin != null
              ? `${edge.margin >= 0 ? "+" : "-"}${Math.abs(edge.margin).toFixed(3)}`
              : "--"
          }
          hi
          positive={hasEdge}
        />
      </div>

      <div className="relative h-1.5 bg-ink-800 rounded">
        <div
          className={`absolute top-0 left-0 h-full rounded ${barColor} transition-[width] duration-500`}
          style={{ width: `${Math.min(100, curW)}%` }}
        />
        <div
          className="absolute -top-0.5 bottom-[-2px] w-[2px] bg-amber-300/90"
          style={{ left: `calc(${Math.min(100, reqW)}% - 1px)` }}
        />
      </div>

      <div className="mt-0.5 text-[8px] text-slate-500 font-mono leading-tight truncate">
        {probLine}
      </div>
    </div>
  );
}

function InlineMetric({
  label,
  value,
  hi,
  positive,
}: {
  label: string;
  value: string;
  hi?: boolean;
  positive?: boolean;
}) {
  const c = hi
    ? positive
      ? "text-emerald-300"
      : "text-rose-300"
    : "text-slate-100";
  return (
    <div className="flex items-baseline gap-1 min-w-0">
      <span className="stat-label text-[7px] leading-tight shrink-0">{label}</span>
      <span className={`text-[11px] leading-tight ${c}`}>{value}</span>
    </div>
  );
}
