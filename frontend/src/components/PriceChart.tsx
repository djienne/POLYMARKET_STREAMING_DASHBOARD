import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useDash } from "../lib/store";
import { fmtLocalHM, fmtLocalHMS } from "../lib/format";

const UP_COLOR = "#34d399"; // emerald-400
const DOWN_COLOR = "#fb7185"; // rose-400
const UP_MODEL_COLOR = "#6ee7b7"; // emerald-300 lighter
const DOWN_MODEL_COLOR = "#fda4af"; // rose-300 lighter
const MARKER_WIN = "#10b981";
const MARKER_LOSS = "#f43f5e";
const MARKER_ENTRY = "#22d3ee";
const TP_LINE = "#facc15";

function toTs(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  return Number.isFinite(t) ? t : null;
}

export default function PriceChart() {
  const up = useDash((s) => s.seriesUp);
  const down = useDash((s) => s.seriesDown);
  const modelUp = useDash((s) => s.modelUp);
  const modelDown = useDash((s) => s.modelDown);
  const markers = useDash((s) => s.markers);
  const position = useDash((s) => s.position.open);
  const polymarket = useDash((s) => s.terminal?.polymarket);
  const slug = useDash((s) => s.terminal?.market?.slug);
  const windowStart = useDash((s) => s.windowStartIso);
  const windowEnd = useDash((s) => s.windowEndIso);

  const startTs = toTs(windowStart);
  const endTs = toTs(windowEnd);
  const haveWindow = startTs != null && endTs != null;

  // Merge all four series keyed by second-precision UTC timestamp
  const data = useMemo(() => {
    const map = new Map<number, any>();
    const push = (t: string, key: string, v: number) => {
      const ts = toTs(t);
      if (ts == null) return;
      if (haveWindow && (ts < startTs! || ts > endTs!)) return;
      // Bucket to the nearest second so poly and model points at the same tick merge
      const bucket = Math.round(ts / 1000) * 1000;
      const row = map.get(bucket) ?? { ts: bucket };
      row[key] = v;
      map.set(bucket, row);
    };
    for (const p of up) push(p.t, "poly_up", p.v);
    for (const p of down) push(p.t, "poly_down", p.v);
    for (const p of modelUp) push(p.t, "model_up", p.v);
    for (const p of modelDown) push(p.t, "model_down", p.v);

    if (haveWindow) {
      const firstPolyUp = firstWindowValue(up, startTs!, endTs!);
      const firstPolyDown = firstWindowValue(down, startTs!, endTs!);
      const startRow = map.get(startTs!) ?? { ts: startTs! };

      if (startRow.poly_up == null) {
        startRow.poly_up = firstPolyUp ?? polymarket?.prob_up ?? undefined;
      }
      if (startRow.poly_down == null) {
        startRow.poly_down = firstPolyDown ?? polymarket?.prob_down ?? undefined;
      }
      if (startRow.poly_up != null || startRow.poly_down != null) {
        map.set(startTs!, startRow);
      }

      // If we only have a current Polymarket quote but no actual series points yet,
      // synthesize a second point "now" so the chart renders a flat carried-back line.
      if (
        firstPolyUp == null &&
        firstPolyDown == null &&
        (polymarket?.prob_up != null || polymarket?.prob_down != null)
      ) {
        const fallbackTs = Math.min(Math.max(Date.now(), startTs!), endTs!);
        const fallbackRow = map.get(fallbackTs) ?? { ts: fallbackTs };
        if (fallbackRow.poly_up == null && polymarket?.prob_up != null) {
          fallbackRow.poly_up = polymarket.prob_up;
        }
        if (fallbackRow.poly_down == null && polymarket?.prob_down != null) {
          fallbackRow.poly_down = polymarket.prob_down;
        }
        map.set(fallbackTs, fallbackRow);
      }
    }

    return Array.from(map.values()).sort((a, b) => a.ts - b.ts);
  }, [up, down, modelUp, modelDown, polymarket, haveWindow, startTs, endTs]);

  const lastUp = up[up.length - 1]?.v ?? polymarket?.prob_up ?? null;
  const lastDown = down[down.length - 1]?.v ?? polymarket?.prob_down ?? null;
  const lastModelUp = modelUp[modelUp.length - 1]?.v ?? null;
  const lastModelDown = modelDown[modelDown.length - 1]?.v ?? null;
  const lastPolyTs = up[up.length - 1]?.t ?? down[down.length - 1]?.t ?? null;
  const nowTs = Date.now();

  // Scope markers to the current window
  const scopedMarkers = useMemo(() => {
    if (!haveWindow) return markers;
    return markers.filter((m) => {
      const ts = toTs(m.t);
      return ts != null && ts >= startTs! && ts <= endTs!;
    });
  }, [markers, haveWindow, startTs, endTs]);

  const tpTarget =
    position?.tp_target != null &&
    position.tp_target >= 0 &&
    position.tp_target <= 1 &&
    (!slug || !position.market_id || position.market_id === slug)
      ? position.tp_target
      : null;

  return (
    <div className="card p-4 h-full flex flex-col">
      <div className="flex items-baseline justify-between mb-2 gap-4">
        <div className="flex items-baseline gap-2">
          <h2 className="card-header">Price · current 15-min market</h2>
          <img
            src="/polymarket.svg"
            alt="Polymarket"
            className="h-4 w-auto opacity-90 translate-y-[2px]"
          />
          <span className="text-[10px] text-slate-500">BTC UP/DOWN</span>
          <span className="text-[10px] text-slate-600 font-mono truncate">
            {slug ?? "—"}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] font-mono">
          <Legend color={UP_COLOR} label="poly UP" value={lastUp} />
          <Legend color={DOWN_COLOR} label="poly DOWN" value={lastDown} />
          <Legend
            color={UP_MODEL_COLOR}
            label="model UP"
            value={lastModelUp}
            dashed
          />
          <Legend
            color={DOWN_MODEL_COLOR}
            label="model DOWN"
            value={lastModelDown}
            dashed
          />
          {lastPolyTs && (
            <span className="text-slate-500">
              last update {fmtLocalHMS(lastPolyTs)}
            </span>
          )}
        </div>
      </div>

      <div className="flex-1 min-h-0 relative">
        {data.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center text-slate-500 text-xs font-mono pointer-events-none">
            waiting for first tick on this market…
          </div>
        )}
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 6, right: 10, bottom: 2, left: 0 }}>
            <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
            <XAxis
              dataKey="ts"
              type="number"
              domain={haveWindow ? [startTs!, endTs!] : ["dataMin", "dataMax"]}
              scale="time"
              allowDataOverflow
              tickFormatter={formatTick}
              stroke="#475569"
              tick={{ fill: "#64748b", fontSize: 10 }}
              ticks={
                haveWindow
                  ? [0, 180, 360, 540, 720, 900].map((s) => startTs! + s * 1000)
                  : undefined
              }
            />
            <YAxis
              domain={[0, 1]}
              ticks={[0, 0.25, 0.5, 0.75, 1]}
              tick={{ fill: "#64748b", fontSize: 10 }}
              stroke="#475569"
              width={32}
              tickFormatter={(v) => v.toFixed(2)}
            />
            <Tooltip
              contentStyle={{
                background: "#0f172a",
                border: "1px solid #334155",
                borderRadius: 8,
                fontSize: 11,
              }}
              labelStyle={{ color: "#94a3b8" }}
              labelFormatter={(v: number) => fmtLocalHMS(v)}
              formatter={(v: number, key: string) => [
                v != null ? v.toFixed(4) : "—",
                key
                  .replace("poly_", "poly ")
                  .replace("model_", "model ")
                  .toUpperCase(),
              ]}
            />
            <ReferenceLine y={0.5} stroke="#334155" strokeDasharray="2 4" />
            {tpTarget != null && (
              <ReferenceLine
                y={tpTarget}
                stroke={TP_LINE}
                strokeWidth={1.5}
                strokeDasharray="6 4"
                strokeOpacity={0.9}
                ifOverflow="extendDomain"
                label={{
                  value: `Take Profit ${tpTarget.toFixed(4)}`,
                  position: "right",
                  fill: TP_LINE,
                  fontSize: 10,
                  fontFamily: "monospace",
                }}
              />
            )}
            {/* Tradeable-zone markers (5m..13m) */}
            {haveWindow && (
              <>
                <ReferenceLine
                  x={startTs! + 300_000}
                  stroke="#f59e0b"
                  strokeDasharray="2 3"
                  strokeOpacity={0.4}
                />
                <ReferenceLine
                  x={startTs! + 780_000}
                  stroke="#f59e0b"
                  strokeDasharray="2 3"
                  strokeOpacity={0.4}
                />
                {/* Current-time cursor */}
                {nowTs >= startTs! && nowTs <= endTs! && (
                  <ReferenceLine
                    x={nowTs}
                    stroke="#22d3ee"
                    strokeOpacity={0.6}
                  />
                )}
              </>
            )}

            <Line
              type="monotone"
              dataKey="model_up"
              name="model UP"
              stroke={UP_MODEL_COLOR}
              strokeWidth={1.5}
              strokeDasharray="4 3"
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="model_down"
              name="model DOWN"
              stroke={DOWN_MODEL_COLOR}
              strokeWidth={1.5}
              strokeDasharray="4 3"
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="poly_up"
              name="poly UP"
              stroke={UP_COLOR}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="poly_down"
              name="poly DOWN"
              stroke={DOWN_COLOR}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />

            {scopedMarkers.flatMap((m, idx) => {
              const ts = toTs(m.t);
              if (ts == null || m.price == null) return [];
              const isEntry = m.kind === "ENTRY";
              const color =
                m.kind === "ENTRY"
                  ? MARKER_ENTRY
                  : m.kind === "WIN"
                    ? MARKER_WIN
                    : MARKER_LOSS;
              const label =
                m.kind === "ENTRY"
                  ? `ENTRY ${m.side ?? ""} ${m.price.toFixed(3)}`
                  : m.kind === "WIN"
                    ? `WIN +$${(m.pnl ?? 0).toFixed(2)}`
                    : `LOSS ${(m.pnl ?? 0) >= 0 ? "+" : "−"}$${Math.abs(m.pnl ?? 0).toFixed(2)}`;
              const base = `${m.t}-${m.kind}-${idx}`;
              // Recharts reads its children by type — ReferenceLine/ReferenceDot must be
              // direct children of LineChart, never wrapped in <g>. Flatten into an array.
              return [
                <ReferenceLine
                  key={`${base}-line`}
                  x={ts}
                  stroke={color}
                  strokeWidth={1.5}
                  strokeDasharray={isEntry ? "3 3" : "0"}
                  strokeOpacity={0.55}
                  isFront
                  label={{
                    value: label,
                    position: "top",
                    offset: 6,
                    fill: color,
                    fontSize: 10,
                    fontFamily: "monospace",
                  }}
                />,
                <ReferenceDot
                  key={`${base}-halo`}
                  x={ts}
                  y={m.price}
                  r={isEntry ? 8 : 10}
                  stroke={color}
                  strokeOpacity={0.35}
                  strokeWidth={2}
                  fill="transparent"
                  isFront
                />,
                <ReferenceDot
                  key={`${base}-dot`}
                  x={ts}
                  y={m.price}
                  r={isEntry ? 5 : 6}
                  stroke={color}
                  fill={isEntry ? "#0f172a" : color}
                  strokeWidth={2.5}
                  isFront
                />,
              ];
            })}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Marker legend row */}
      <div className="mt-2 flex items-center gap-3 text-[10px] font-mono text-slate-500">
        <MarkerHint color={MARKER_ENTRY} label="ENTRY" hollow />
        <MarkerHint color={MARKER_WIN} label="WIN / TP" />
        <MarkerHint color={MARKER_LOSS} label="LOSS / SL" />
        <MarkerHint color={TP_LINE} label="ACTIVE TP" line />
        <span className="ml-auto text-slate-600">
          orange ticks = tradeable zone (5–13m)
        </span>
      </div>
    </div>
  );
}

function Legend({
  color,
  label,
  value,
  dashed,
}: {
  color: string;
  label: string;
  value: number | null;
  dashed?: boolean;
}) {
  return (
    <span className="flex items-center gap-1.5">
      <svg width="14" height="4">
        <line
          x1="0"
          y1="2"
          x2="14"
          y2="2"
          stroke={color}
          strokeWidth="2"
          strokeDasharray={dashed ? "3 2" : undefined}
        />
      </svg>
      <span className="text-slate-400">{label}</span>
      <span style={{ color }}>
        {value != null ? value.toFixed(4) : "—"}
      </span>
    </span>
  );
}

function MarkerHint({
  color,
  label,
  hollow,
  line,
}: {
  color: string;
  label: string;
  hollow?: boolean;
  line?: boolean;
}) {
  return (
    <span className="flex items-center gap-1.5">
      {line ? (
        <svg width="14" height="6" aria-hidden="true">
          <line
            x1="0"
            y1="3"
            x2="14"
            y2="3"
            stroke={color}
            strokeWidth="2"
            strokeDasharray="4 3"
          />
        </svg>
      ) : (
        <span
          className="inline-block w-2 h-2 rounded-full"
          style={{
            background: hollow ? "transparent" : color,
            border: `2px solid ${color}`,
          }}
        />
      )}
      <span>{label}</span>
    </span>
  );
}

function formatTick(ts: number): string {
  return fmtLocalHM(ts);
}

function firstWindowValue(
  series: { t: string; v: number }[],
  startTs: number,
  endTs: number,
): number | null {
  for (const p of series) {
    const ts = toTs(p.t);
    if (ts == null) continue;
    if (ts < startTs || ts > endTs) continue;
    return p.v;
  }
  return null;
}
