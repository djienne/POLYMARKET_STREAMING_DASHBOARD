import { useMemo } from "react";
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

export default function EquitySparkline() {
  const series = useDash((s) => s.equitySeries);
  const start = useDash((s) => s.instance?.starting_capital ?? 1000);

  const data = useMemo(() => {
    return series
      .map((p) => {
        const ts = new Date(p.t).getTime();
        return Number.isFinite(ts) ? { ts, v: p.v } : null;
      })
      .filter((x): x is { ts: number; v: number } => x != null)
      .sort((a, b) => a.ts - b.ts);
  }, [series]);

  const last = data[data.length - 1]?.v ?? start;
  const closedTrades = Math.max(data.length - 1, 0);
  const up = last >= start;
  const color = up ? "#34d399" : "#fb7185";

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
              domain={["dataMin - 20", "dataMax + 20"]}
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
