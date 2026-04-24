import { AnimatePresence, motion } from "framer-motion";
import { useDash } from "../lib/store";
import { fmtLocalHMS, fmtMoney } from "../lib/format";

export default function PositionCard() {
  const pos = useDash((s) => s.position);
  const mode = useDash((s) => s.mode);
  const terminal = useDash((s) => s.terminal);
  const flashes = useDash((s) => s.flashQueue);
  const hasFlash = flashes.length > 0;

  const open = pos.open;
  const dirUp = open?.direction === "UP";
  const dirColor = dirUp ? "text-emerald-300" : "text-rose-300";
  const dirRing = dirUp ? "ring-emerald-400/40" : "ring-rose-400/40";

  let livePnL: number | null = null;
  if (open && terminal?.polymarket) {
    const market =
      open.direction === "UP"
        ? terminal.polymarket.prob_up
        : terminal.polymarket.prob_down;
    if (market != null && open.shares) {
      livePnL = (market - open.entry_price) * open.shares;
    }
  }

  return (
    <div
      className={`card p-3 h-full flex flex-col relative overflow-hidden transition-shadow ${
        open ? `ring-1 ${dirRing}` : ""
      }`}
    >
      <AnimatePresence>
        {hasFlash && open && (
          <motion.div
            key="ring"
            initial={{ opacity: 0.6, scale: 1 }}
            animate={{ opacity: 0, scale: 1.3 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 1.2, ease: "easeOut" }}
            className={`absolute inset-2 rounded-xl ${
              dirUp ? "bg-emerald-500/10" : "bg-rose-500/10"
            } pointer-events-none`}
          />
        )}
      </AnimatePresence>

      <div className="flex items-baseline justify-between mb-2">
        <h2 className="card-header">Position</h2>
        {mode === "live" ? (
          <GracePill />
        ) : (
          <span className="chip chip-mute text-[10px]">grid - n/a grace</span>
        )}
      </div>

      {open ? (
        <div className="space-y-2">
          <div className="flex items-baseline gap-2 flex-wrap">
            <span className={`text-lg font-semibold ${dirColor}`}>
              {open.direction}
            </span>
            <span className="text-slate-500 text-[11px] font-mono">
              opened {fmtLocalHMS(open.entered_at)}
            </span>
            {open.entry_edge_ratio != null && (
              <span
                title="Edge ratio the trader captured at fill (model_prob / executable market price). Higher = better-quality entry."
                className={`chip font-mono text-[10px] ${
                  open.entry_edge_ratio >= 1.2
                    ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/30"
                    : open.entry_edge_ratio >= 1.05
                      ? "bg-cyan-500/10 text-cyan-300 border-cyan-500/30"
                      : "bg-amber-500/10 text-amber-300 border-amber-500/30"
                }`}
              >
                <span className="text-slate-400/80">edge</span>
                <span className="tabular-nums">
                  {open.entry_edge_ratio.toFixed(2)}x
                </span>
              </span>
            )}
          </div>
          <div className="grid grid-cols-3 gap-x-3 gap-y-1.5">
            <Stat label="entry" value={open.entry_price.toFixed(4)} />
            <Stat label="shares" value={open.shares.toFixed(3)} />
            <Stat
              label="notional"
              value={
                open.notional != null ? `$${open.notional.toFixed(2)}` : "--"
              }
            />
            <Stat
              label="tp"
              value={open.tp_target != null ? open.tp_target.toFixed(4) : "--"}
            />
            <Stat
              label="sl"
              value={
                open.sl_target != null && open.sl_target > 0
                  ? open.sl_target.toFixed(4)
                  : "off"
              }
            />
            <Stat
              label="unrealized"
              value={fmtMoney(livePnL)}
              color={
                livePnL == null
                  ? "text-slate-400"
                  : livePnL >= 0
                    ? "text-emerald-300"
                    : "text-rose-300"
              }
            />
          </div>
        </div>
      ) : (
        <div className="flex-1 min-h-0 flex items-center">
          <div className="w-full rounded-xl border border-ink-800/80 bg-[linear-gradient(180deg,rgba(15,23,42,0.42),rgba(15,23,42,0.16))] px-3 py-3">
            <div className="flex items-center justify-between gap-2">
              <div className="text-sm font-semibold text-slate-200">Flat</div>
              <span className="chip chip-mute text-[10px]">no open position</span>
            </div>
            <div className="mt-1.5 text-xs leading-relaxed text-slate-500">
              Waiting for a valid edge before entering the next trade.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <div>
      <div className="stat-label">{label}</div>
      <div className={`font-mono text-sm ${color ?? "text-slate-100"}`}>
        {value}
      </div>
    </div>
  );
}

function GracePill() {
  const pos = useDash((s) => s.position);
  const rem = pos.grace_remaining_s;
  if (rem == null || rem <= 0) {
    return <span className="chip chip-ok text-[10px]">grace clear</span>;
  }
  return (
    <span className="chip chip-warn text-[10px] font-mono">
      grace {rem.toFixed(0)}s
    </span>
  );
}
