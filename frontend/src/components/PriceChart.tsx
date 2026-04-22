import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
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
const MODEL_DISPLAY_LOCK_S = 20;

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
  const window = useDash((s) => s.window);
  const windowElapsed = window?.elapsed_s ?? null;
  const windowStart = useDash((s) => s.windowStartIso);
  const windowEnd = useDash((s) => s.windowEndIso);

  const startTs = toTs(windowStart);
  const endTs = toTs(windowEnd);
  const haveWindow = startTs != null && endTs != null;
  const modelDisplayLockEndTs =
    haveWindow ? Math.min(startTs! + MODEL_DISPLAY_LOCK_S * 1000, endTs!) : null;
  const lockModelDisplay =
    haveWindow && windowElapsed != null && windowElapsed < MODEL_DISPLAY_LOCK_S;
  const blockedFirstMs = (window?.no_trade_first_s ?? 300) * 1000;
  const blockedLastMs = (window?.no_trade_last_s ?? 120) * 1000;
  const blockedLastStartTs =
    haveWindow ? Math.max(startTs!, endTs! - blockedLastMs) : null;

  // Merge all four series keyed by second-precision UTC timestamp
  const data = useMemo(() => {
    const map = new Map<number, any>();
    const visibleModelUp =
      modelLockSeries(modelUp, modelDisplayLockEndTs);
    const visibleModelDown =
      modelLockSeries(modelDown, modelDisplayLockEndTs);
    const fallbackNowTs = haveWindow
      ? Math.floor(Math.min(Math.max(Date.now(), startTs!), endTs!) / 1000) * 1000
      : null;
    const bucketFor = (ts: number, key: string): number | null => {
      if (haveWindow && (ts < startTs! || ts > endTs!)) return null;
      let bucket = Math.floor(ts / 1000) * 1000;
      return bucket;
    };
    const push = (t: string, key: string, v: number) => {
      const ts = toTs(t);
      if (ts == null) return;
      const bucket = bucketFor(ts, key);
      if (bucket == null) return;
      const row = map.get(bucket) ?? { ts: bucket };
      row[key] = v;
      map.set(bucket, row);
    };
    for (const p of up) push(p.t, "poly_up", p.v);
    for (const p of down) push(p.t, "poly_down", p.v);
    for (const p of visibleModelUp) push(p.t, "model_up", p.v);
    for (const p of visibleModelDown) push(p.t, "model_down", p.v);

    if (haveWindow) {
      // Restore the poly-line carry-back: seed t=0 with the first observed poll
      // (or live polymarket snapshot) so the solid poly line has an anchor.
      const firstPolyUp = firstWindowPoint(up, startTs!, endTs!)?.v ?? null;
      const firstPolyDown = firstWindowPoint(down, startTs!, endTs!)?.v ?? null;
      const startRow = map.get(startTs!) ?? { ts: startTs! };

      if (startRow.poly_up == null) {
        startRow.poly_up = firstPolyUp ?? polymarket?.prob_up ?? undefined;
      }
      if (startRow.poly_down == null) {
        startRow.poly_down = firstPolyDown ?? polymarket?.prob_down ?? undefined;
      }

      // Seed the MODEL series at t=0 with a 50/50 prior so the chart doesn't
      // show a 7 s gap while calibration computes the first real model
      // probability. Model lines are already dashed, so the seeded segment
      // naturally reads as "estimated until the model catches up".
      const firstModelUp = firstWindowPoint(visibleModelUp, startTs!, endTs!);
      const firstModelDown = firstWindowPoint(visibleModelDown, startTs!, endTs!);
      startRow.model_up = 0.5;
      startRow.model_down = 0.5;
      if (
        startRow.poly_up != null ||
        startRow.poly_down != null ||
        startRow.model_up != null ||
        startRow.model_down != null
      ) {
        map.set(startTs!, startRow);
      }

      if (modelDisplayLockEndTs != null) {
        const syntheticEndTs =
          fallbackNowTs != null
            ? Math.min(fallbackNowTs, modelDisplayLockEndTs)
            : modelDisplayLockEndTs;
        for (let ts = startTs! + 1000; ts <= syntheticEndTs; ts += 1000) {
          const row = map.get(ts) ?? { ts };
          row.model_up = 0.5;
          row.model_down = 0.5;
          map.set(ts, row);
        }
      }

      const pinModelSeed = (
        key: "model_up" | "model_down",
        firstPoint: { ts: number; v: number } | null,
      ) => {
        if (firstPoint == null) {
          if (fallbackNowTs == null) return;
          const row = map.get(fallbackNowTs) ?? { ts: fallbackNowTs };
          if (row[key] == null) row[key] = 0.5;
          map.set(fallbackNowTs, row);
          return;
        }
        const firstBucket = bucketFor(firstPoint.ts, key);
        if (firstBucket == null) return;
        const handoffTs = Math.max(modelDisplayLockEndTs ?? startTs!, firstBucket - 1000);
        const row = map.get(handoffTs) ?? { ts: handoffTs };
        if (row[key] == null) row[key] = 0.5;
        map.set(handoffTs, row);
      };

      // If no real model point has arrived yet, extend the 0.5 seed to "now"
      // so the dashed model line is actually visible. Once the first real
      // point exists, keep the seed pinned until one second before that point
      // so the handoff doesn't visually "snap" backward.
      pinModelSeed("model_up", firstModelUp);
      pinModelSeed("model_down", firstModelDown);

      // If we only have a current Polymarket quote but no actual series points
      // yet, synthesize a second poly point "now" so the solid line renders.
      if (
        firstPolyUp == null &&
        firstPolyDown == null &&
        fallbackNowTs != null &&
        (polymarket?.prob_up != null || polymarket?.prob_down != null)
      ) {
        const fallbackRow = map.get(fallbackNowTs) ?? { ts: fallbackNowTs };
        if (fallbackRow.poly_up == null && polymarket?.prob_up != null) {
          fallbackRow.poly_up = polymarket.prob_up;
        }
        if (fallbackRow.poly_down == null && polymarket?.prob_down != null) {
          fallbackRow.poly_down = polymarket.prob_down;
        }
        map.set(fallbackNowTs, fallbackRow);
      }
    }

    return Array.from(map.values()).sort((a, b) => a.ts - b.ts);
  }, [
    up,
    down,
    modelUp,
    modelDown,
    polymarket,
    haveWindow,
    startTs,
    endTs,
    windowElapsed,
    lockModelDisplay,
    modelDisplayLockEndTs,
  ]);

  const lastUp = up[up.length - 1]?.v ?? polymarket?.prob_up ?? null;
  const lastDown = down[down.length - 1]?.v ?? polymarket?.prob_down ?? null;
  const visibleModelUp =
    modelLockSeries(modelUp, modelDisplayLockEndTs);
  const visibleModelDown =
    modelLockSeries(modelDown, modelDisplayLockEndTs);
  const lastModelUp = lockModelDisplay ? 0.5 : (visibleModelUp[visibleModelUp.length - 1]?.v ?? 0.5);
  const lastModelDown = lockModelDisplay ? 0.5 : (visibleModelDown[visibleModelDown.length - 1]?.v ?? 0.5);
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
            {/* No-trade zone shading (under the lines, behind boundary ticks) */}
            {haveWindow && (
              <>
                <ReferenceArea
                  x1={startTs!}
                  x2={startTs! + blockedFirstMs}
                  fill="#f59e0b"
                  fillOpacity={0.07}
                  stroke="none"
                  label={{
                    value: "settling · no entries",
                    position: "insideTop",
                    offset: 6,
                    fill: "#fcd34d",
                    fontSize: 10,
                    fontFamily: "monospace",
                  }}
                />
                <ReferenceArea
                  x1={blockedLastStartTs!}
                  x2={endTs!}
                  fill="#f43f5e"
                  fillOpacity={0.07}
                  stroke="none"
                  label={{
                    value: "closing · exits only",
                    position: "insideTop",
                    offset: 6,
                    fill: "#fda4af",
                    fontSize: 10,
                    fontFamily: "monospace",
                  }}
                />
                {/* Crisp boundaries on top of the shading */}
                <ReferenceLine
                  x={startTs! + blockedFirstMs}
                  stroke="#f59e0b"
                  strokeDasharray="2 3"
                  strokeOpacity={0.5}
                />
                <ReferenceLine
                  x={blockedLastStartTs!}
                  stroke="#f43f5e"
                  strokeDasharray="2 3"
                  strokeOpacity={0.5}
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
              type="linear"
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
              type="linear"
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
              type="linear"
              dataKey="poly_up"
              name="poly UP"
              stroke={UP_COLOR}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
            <Line
              type="linear"
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
        <span className="ml-auto flex items-center gap-3 text-slate-500">
          <span className="inline-flex items-center gap-1.5">
            <span
              className="inline-block h-2 w-3 rounded-sm"
              style={{ backgroundColor: "#f59e0b", opacity: 0.45 }}
            />
            <span>0–5m no entries</span>
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span
              className="inline-block h-2 w-3 rounded-sm"
              style={{ backgroundColor: "#f43f5e", opacity: 0.45 }}
            />
            <span>13–15m exits only</span>
          </span>
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

function formatSec(s: number): string {
  const m = Math.floor(Math.max(0, s) / 60);
  const r = Math.floor(Math.max(0, s) % 60);
  return `${m}:${r.toString().padStart(2, "0")}`;
}

function firstWindowPoint(
  series: { t: string; v: number }[],
  startTs: number,
  endTs: number,
  minTs: number = startTs,
): { ts: number; v: number } | null {
  for (const p of series) {
    const ts = toTs(p.t);
    if (ts == null) continue;
    if (ts < Math.max(startTs, minTs) || ts > endTs) continue;
    return { ts, v: p.v };
  }
  return null;
}

function modelLockSeries(
  series: { t: string; v: number }[],
  minTs: number | null,
): { t: string; v: number }[] {
  if (minTs == null) return series;
  return series.filter((p) => {
    const ts = toTs(p.t);
    return ts != null && ts >= minTs;
  });
}
