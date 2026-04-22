import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useDash } from "../lib/store";
import { fmtLocalDate, fmtLocalFull, fmtLocalHM } from "../lib/format";

const ZOOM_ROTATE_MS = 60_000;
const ZOOM_4D_MS = 4 * 86_400_000;

export default function EquitySparkline() {
  const series = useDash((s) => s.equitySeries);
  const windowStartIso = useDash((s) => s.windowStartIso);
  // Prefer the live instance's starting_capital; fall back to the trader's
  // configured starting_capital (live: 100, paper grid: 1000) so a fresh run
  // with no trades still renders on a sensible scale.
  const start = useDash(
    (s) => s.instance?.starting_capital ?? s.sharedConfig.starting_capital ?? 100,
  );

  const [mode, setMode] = useState<"all" | "4d">("all");
  useEffect(() => {
    const id = setInterval(
      () => setMode((m) => (m === "all" ? "4d" : "all")),
      ZOOM_ROTATE_MS,
    );
    return () => clearInterval(id);
  }, []);

  const data = useMemo(() => {
    const full = series
      .map((p) => {
        const ts = new Date(p.t).getTime();
        return Number.isFinite(ts) ? { ts, v: p.v } : null;
      })
      .filter((x): x is { ts: number; v: number } => x != null)
      .sort((a, b) => a.ts - b.ts);
    if (mode === "4d") {
      const cutoff = Date.now() - ZOOM_4D_MS;
      const zoomed = full.filter((p) => p.ts >= cutoff);
      if (zoomed.length >= 2) return zoomed;
    }
    if (full.length === 0) {
      const now = Date.now();
      const seedStart = windowStartIso != null ? Date.parse(windowStartIso) : NaN;
      const startTs =
        Number.isFinite(seedStart) && seedStart < now
          ? seedStart
          : now - 15 * 60 * 1000;
      return [
        { ts: startTs, v: start },
        { ts: Math.max(startTs + 1000, now), v: start },
      ];
    }
    return full;
  }, [series, mode, start, windowStartIso]);

  const last = data[data.length - 1]?.v ?? start;
  const closedTrades = Math.max(series.length - 1, 0);
  const up = last >= start;
  const color = up ? "#34d399" : "#fb7185";
  const yMin = useMemo(() => {
    const dataMin = data.reduce(
      (min, point) => Math.min(min, point.v),
      Number.POSITIVE_INFINITY,
    );
    if (!Number.isFinite(dataMin)) return Math.max(0, start * 0.9);
    // For the live $100 baseline, keep the chart tight: start at $99 unless
    // equity actually goes below $100, then give it $1 of breathing room.
    if (start <= 100) {
      return dataMin < 100 ? Math.max(0, dataMin - 1) : 99;
    }
    return Math.max(0, start * 0.9);
  }, [data, start]);

  // Build 5 evenly spaced ticks so recharts doesn't pick dense auto-ticks
  const explicitTicks = useMemo(() => {
    if (data.length < 2) return undefined;
    const min = data[0].ts;
    const max = data[data.length - 1].ts;
    const n = 5;
    return Array.from({ length: n }, (_, i) =>
      Math.round(min + ((max - min) * i) / (n - 1)),
    );
  }, [data]);
  const spansMultipleDays =
    data.length >= 2 && data[data.length - 1].ts - data[0].ts > 86_400_000;

  return (
    <div className="card p-4 h-full flex flex-col">
      <div className="flex items-baseline justify-between mb-1">
        <h2 className="card-header">Equity curve</h2>
        <div className="text-right">
          <div
            className={`font-mono text-lg ${
              up ? "text-emerald-300" : "text-rose-300"
            }`}
          >
            ${last.toFixed(2)}
          </div>
          <div className="text-[10px] text-slate-500 font-mono">
            {closedTrades} closed trades
          </div>
        </div>
      </div>
      <div className="flex-1 min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="equity" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.35} />
                <stop offset="100%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="ts"
              type="number"
              domain={["dataMin", "dataMax"]}
              scale="time"
              ticks={explicitTicks}
              tickFormatter={(v) => formatTick(v, spansMultipleDays)}
              stroke="#475569"
              tick={{ fill: "#64748b", fontSize: 10 }}
              minTickGap={80}
            />
            <YAxis
              domain={[
                yMin,
                (dataMax: number) => Math.ceil(dataMax + Math.max(2, start * 0.02)),
              ]}
              allowDataOverflow
              tick={{ fill: "#64748b", fontSize: 10 }}
              stroke="#475569"
              width={48}
              tickFormatter={(v) => `$${v.toFixed(0)}`}
            />
            <Tooltip
              contentStyle={{
                background: "#0f172a",
                border: "1px solid #334155",
                borderRadius: 8,
                fontSize: 11,
              }}
              labelStyle={{ color: "#94a3b8" }}
              labelFormatter={(v: number) => fmtLocalFull(v)}
              formatter={(v: number) => [`$${v.toFixed(2)}`, "equity"]}
            />
            <Area
              type="monotone"
              dataKey="v"
              stroke={color}
              strokeWidth={2}
              fill="url(#equity)"
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function formatTick(ts: number, multiDay: boolean): string {
  return multiDay ? fmtLocalDate(ts) : fmtLocalHM(ts);
}
