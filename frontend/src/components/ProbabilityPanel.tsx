import { useMemo } from "react";
import { useDash } from "../lib/store";
import { fmtProb } from "../lib/format";

type Row = {
  label: string;
  above: number | null;
  below: number | null;
  preferred?: boolean;
  available: boolean;
};

export default function ProbabilityPanel() {
  const terminal = useDash((s) => s.terminal);
  const calActive = useDash((s) => s.calibration.active);

  const probs = terminal?.probabilities;
  const poly = terminal?.polymarket;
  const pref = probs?.preferred_model ?? "";

  const rows = useMemo<Row[]>(() => {
    // The bot uses avg_prob when present (polymarket_edge.py: prob_above = avg_above).
    // Only if avg is missing does it fall back to the preferred single-model value.
    const avgUsed =
      probs?.avg_above != null || probs?.avg_below != null;
    const ssviUsed = !avgUsed && pref === "ssvi_surface";
    const hestonUsed = !avgUsed && pref === "heston";
    return [
      {
        label: "SSVI surface (BL)",
        above: probs?.ssvi_surface_above ?? null,
        below: probs?.ssvi_surface_below ?? null,
        preferred: ssviUsed,
        available:
          probs?.ssvi_surface_above != null || probs?.ssvi_surface_below != null,
      },
      {
        label: "SSVI + Monte Carlo",
        above: probs?.mc_above ?? null,
        below: probs?.mc_below ?? null,
        available: probs?.mc_above != null || probs?.mc_below != null,
      },
      {
        label: "Heston (skipped by default)",
        above: probs?.heston_above ?? null,
        below: probs?.heston_below ?? null,
        preferred: hestonUsed,
        available: probs?.heston_above != null || probs?.heston_below != null,
      },
      {
        label: "Average of SSVI BL and MC",
        above: probs?.avg_above ?? null,
        below: probs?.avg_below ?? null,
        preferred: avgUsed,
        available: probs?.avg_above != null || probs?.avg_below != null,
      },
    ];
  }, [probs, pref]);

  return (
    <div className={`card p-4 relative overflow-hidden h-full flex flex-col ${calActive ? "opacity-90" : ""}`}>
      {calActive && (
        <div className="absolute inset-0 pointer-events-none shimmer-bar animate-shimmer" />
      )}
      <div className="flex items-baseline justify-between mb-3 gap-3">
        <div className="flex items-baseline gap-2 flex-wrap">
          <h2 className="card-header">Model probabilities vs market</h2>
          <span className="text-[10px] text-slate-500 inline-flex items-center gap-1.5">
            <span>model fit from</span>
            <img
              src="/deribit.svg"
              alt="Deribit"
              className="h-4 w-auto"
            />
            <span>BTC options</span>
          </span>
        </div>
        <div className="flex items-center gap-2">
          {probs?.bl_mc_divergence != null &&
            Math.abs(probs.bl_mc_divergence) > 0.1 && (
              <span className="chip chip-warn font-mono">
                divergence {probs.bl_mc_divergence.toFixed(3)}
              </span>
            )}
          <img src="/polymarket.svg" alt="Polymarket" className="h-4 w-auto opacity-90" />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 flex-1 min-h-0">
        <SideColumn
          side="UP"
          rows={rows.map((r) => ({ ...r, value: r.above }))}
          marketProb={poly?.prob_up ?? null}
        />
        <SideColumn
          side="DOWN"
          rows={rows.map((r) => ({ ...r, value: r.below }))}
          marketProb={poly?.prob_down ?? null}
        />
      </div>
    </div>
  );
}

function SideColumn({
  side,
  rows,
  marketProb,
}: {
  side: "UP" | "DOWN";
  rows: (Row & { value: number | null })[];
  marketProb: number | null;
}) {
  const sideColor =
    side === "UP" ? "text-emerald-300" : "text-rose-300";
  const sideBg =
    side === "UP" ? "bg-emerald-400/70" : "bg-rose-400/70";

  return (
    <div>
      <div className="flex items-baseline justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className={`font-semibold ${sideColor} tracking-wide`}>
            {side}
          </span>
          <span className="text-xs text-slate-500">
            Polymarket implied
          </span>
        </div>
        <span className={`font-mono text-lg ${sideColor}`}>
          {fmtProb(marketProb)}
        </span>
      </div>

      <div className="space-y-2">
        {rows.map((r) => (
          <ProbRow
            key={r.label}
            label={r.label}
            value={r.value}
            marketProb={marketProb}
            sideBg={sideBg}
            preferred={r.preferred}
            available={r.available}
          />
        ))}
      </div>
    </div>
  );
}

function ProbRow({
  label,
  value,
  marketProb,
  sideBg,
  preferred,
  available,
}: {
  label: string;
  value: number | null;
  marketProb: number | null;
  sideBg: string;
  preferred?: boolean;
  available: boolean;
}) {
  const w = value != null ? Math.max(0, Math.min(1, value)) * 100 : 0;
  const mw = marketProb != null ? Math.max(0, Math.min(1, marketProb)) * 100 : null;
  return (
    <div>
      <div className="flex items-center justify-between text-[11px] mb-1">
        <div className="flex items-center gap-2">
          <span className={`${preferred ? "text-cyan-200" : "text-slate-400"}`}>
            {label}
          </span>
          {preferred && (
            <span className="chip chip-ok text-[9px] py-[1px] px-1.5">
              used
            </span>
          )}
          {!available && (
            <span className="text-slate-600 text-[10px]">n/a</span>
          )}
        </div>
        <span className="font-mono text-slate-200">{fmtProb(value)}</span>
      </div>
      <div className="relative h-2 bg-ink-800 rounded">
        <div
          className={`absolute top-0 left-0 h-full ${sideBg} rounded transition-[width] duration-500`}
          style={{ width: `${w}%` }}
        />
        {mw != null && (
          <div
            className="absolute -top-0.5 bottom-[-2px] w-[2px] bg-white/80"
            style={{ left: `calc(${mw}% - 1px)` }}
            title={`Polymarket ${mw.toFixed(1)}%`}
          />
        )}
      </div>
    </div>
  );
}
