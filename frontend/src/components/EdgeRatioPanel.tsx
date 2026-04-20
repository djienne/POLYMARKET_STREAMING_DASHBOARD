import { useDash } from "../lib/store";
import { fmtRatio } from "../lib/format";
import type { EdgeRatio, WindowZone } from "../lib/types";

export default function EdgeRatioPanel() {
  const edgeUp = useDash((s) => s.edgeUp);
  const edgeDown = useDash((s) => s.edgeDown);
  const window = useDash((s) => s.window);
  const zone: WindowZone = window?.zone ?? "unknown";
  const blockReason =
    zone === "blocked_first"
      ? "settling · first 5m"
      : zone === "blocked_last"
        ? "closing · last 2m"
        : zone === "expired"
          ? "expired"
          : null;

  return (
    <div className="card p-4 h-full flex flex-col overflow-hidden">
      <div className="flex items-baseline justify-between mb-2">
        <h2 className="card-header">Edge ratio · entry check</h2>
        {blockReason && (
          <span className="chip chip-warn text-[10px] font-mono">
            entries blocked · {blockReason}
          </span>
        )}
      </div>
      <div className="grid grid-cols-1 gap-2 flex-1 min-h-0">
        <EdgeRow edge={edgeUp} blockReason={blockReason} />
        <EdgeRow edge={edgeDown} blockReason={blockReason} />
      </div>
    </div>
  );
}

function EdgeRow({
  edge,
  blockReason,
}: {
  edge: EdgeRatio | null;
  blockReason: string | null;
}) {
  if (!edge) {
    return (
      <div className="border border-ink-800 rounded-lg p-3 text-slate-500 text-sm">
        Waiting for probabilities…
      </div>
    );
  }

  const hasEdge = edge.has_edge === true;
  const isBlocked = blockReason != null;
  const sideColor =
    edge.side === "UP" ? "text-emerald-300" : "text-rose-300";

  const max = Math.max(edge.current_ratio ?? 0, edge.required_ratio ?? 0, 1.5);
  const curW =
    edge.current_ratio != null ? (edge.current_ratio / max) * 100 : 0;
  const reqW =
    edge.required_ratio != null ? (edge.required_ratio / max) * 100 : 0;

  // Top-line status: blocked > edge math
  let chipClass: string;
  let chipText: string;
  if (isBlocked) {
    chipClass = "chip-warn";
    chipText = hasEdge ? "edge ✓ · blocked" : "blocked";
  } else if (edge.has_edge == null) {
    chipClass = "chip-mute";
    chipText = "—";
  } else if (hasEdge) {
    chipClass = "chip-up";
    chipText = "edge ✓";
  } else {
    chipClass = "chip-down";
    chipText = "no edge";
  }

  // The bar color should also reflect the effective entry-eligibility, not just math.
  const barColor = isBlocked
    ? "bg-amber-500/50"
    : hasEdge
      ? "bg-emerald-500/60"
      : "bg-rose-500/50";

  return (
    <div className="rounded-lg border border-ink-800 bg-ink-900/40 p-3">
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-baseline gap-2">
          <span className={`font-semibold tracking-wide ${sideColor}`}>
            {edge.side}
          </span>
          <span className="text-[10px] uppercase tracking-widest text-slate-500">
            model / market
          </span>
        </div>
        <span className={`chip ${chipClass} font-mono`}>{chipText}</span>
      </div>

      <div className="grid grid-cols-3 gap-2 mb-2">
        <Mini
          label="current"
          value={fmtRatio(edge.current_ratio)}
          hi
          positive={hasEdge}
        />
        <Mini label="required" value={fmtRatio(edge.required_ratio)} />
        <Mini
          label="margin"
          value={
            edge.margin != null
              ? (edge.margin >= 0 ? "+" : "−") +
                Math.abs(edge.margin).toFixed(3)
              : "—"
          }
          hi
          positive={hasEdge}
        />
      </div>

      <div className="relative h-2 bg-ink-800 rounded">
        <div
          className={`absolute top-0 left-0 h-full rounded ${barColor} transition-[width] duration-500`}
          style={{ width: `${Math.min(100, curW)}%` }}
        />
        <div
          className="absolute -top-0.5 bottom-[-2px] w-[2px] bg-amber-300/90"
          style={{ left: `calc(${Math.min(100, reqW)}% - 1px)` }}
        />
      </div>
    </div>
  );
}

function Mini({
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
    <div>
      <div className="stat-label text-[9px]">{label}</div>
      <div className={`font-mono text-sm ${c}`}>{value}</div>
    </div>
  );
}
