import { useDash } from "../lib/store";

export default function MarketInfoCard() {
  const terminal = useDash((s) => s.terminal);
  const window = useDash((s) => s.window);
  const m = terminal?.market;
  const poly = terminal?.polymarket;
  const liveTimeLeft =
    window != null ? Math.max(0, window.total_s - window.elapsed_s) : null;

  const barrierDelta =
    m?.spot_price != null && m.barrier != null
      ? m.spot_price - m.barrier
      : null;
  const barrierPct =
    barrierDelta != null && m?.barrier
      ? (barrierDelta / m.barrier) * 100
      : null;

  return (
    <div className="card p-4 h-full flex flex-col">
      <div className="flex items-baseline justify-between mb-1">
        <h2 className="card-header">Current market</h2>
        {m?.direction && (
          <span
            className={`chip font-mono ${
              m.direction.toLowerCase() === "up" ? "chip-up" : "chip-down"
            }`}
          >
            {m.direction.toUpperCase()}
          </span>
        )}
      </div>

      <div className="text-[10px] text-slate-500 font-mono truncate mb-3">
        {m?.slug ?? "—"}
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-2 flex-1 min-h-0">
        <Kv label="Spot">
          <span className="font-mono text-slate-100 text-sm">
            {m?.spot_price != null
              ? `$${m.spot_price.toLocaleString(undefined, {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}`
              : "—"}
          </span>
        </Kv>
        <Kv label="Barrier">
          <span className="font-mono text-slate-100 text-sm">
            {m?.barrier != null
              ? `$${m.barrier.toLocaleString(undefined, {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}`
              : "—"}
          </span>
          {barrierDelta != null && (
            <span
              className={`ml-1 text-[10px] font-mono ${
                barrierDelta >= 0 ? "text-emerald-300" : "text-rose-300"
              }`}
            >
              {(barrierDelta >= 0 ? "+" : "−") +
                "$" +
                Math.abs(barrierDelta).toFixed(2)}
              {barrierPct != null && (
                <span className="opacity-70">
                  {" "}
                  {(barrierPct >= 0 ? "+" : "−") +
                    Math.abs(barrierPct).toFixed(3) +
                    "%"}
                </span>
              )}
            </span>
          )}
        </Kv>
        <Kv label="Poly bid / ask">
          <span className="font-mono text-slate-100 text-sm">
            {poly?.best_bid != null ? poly.best_bid.toFixed(3) : "—"}
            <span className="text-slate-500"> / </span>
            {poly?.best_ask != null ? poly.best_ask.toFixed(3) : "—"}
          </span>
        </Kv>
        <Kv label="Time left">
          <span className="font-mono text-slate-100 text-sm">
            {liveTimeLeft != null
              ? formatSeconds(liveTimeLeft)
              : m?.ttm_seconds != null
                ? formatSeconds(m.ttm_seconds)
                : "—"}
          </span>
        </Kv>
      </div>
    </div>
  );
}

function Kv({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="stat-label mb-0.5">{label}</div>
      <div className="flex items-baseline gap-1 truncate">{children}</div>
    </div>
  );
}

function formatSeconds(s: number): string {
  const m = Math.max(0, Math.floor(s / 60));
  const r = Math.max(0, Math.floor(s % 60));
  return `${m}:${r.toString().padStart(2, "0")}`;
}
