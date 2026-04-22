import { AnimatePresence, motion } from "framer-motion";
import { useDash } from "../lib/store";
import { fmtLocalHMS, fmtMoney, fmtPct } from "../lib/format";
import type { TradeEvent } from "../lib/types";

export default function TradeFeed() {
  const trades = useDash((s) => s.trades);

  return (
    <div className="card p-3.5 h-full flex flex-col">
      <div className="flex items-baseline justify-between mb-2.5">
        <h2 className="card-header">Trade feed</h2>
        <span className="text-[11px] text-slate-500 font-mono">
          last {trades.length}
        </span>
      </div>

      {trades.length === 0 ? (
        <div className="flex-1 min-h-0 flex items-center justify-center">
          <div className="w-full rounded-xl border border-dashed border-ink-700/90 bg-[linear-gradient(180deg,rgba(15,23,42,0.52),rgba(15,23,42,0.22))] px-4 py-6 text-center">
            <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full border border-cyan-500/25 bg-cyan-500/10 shadow-[0_0_20px_rgba(34,211,238,0.08)]">
              <span className="h-2.5 w-2.5 rounded-full bg-cyan-300 shadow-[0_0_10px_rgba(103,232,249,0.8)]" />
            </div>
            <div className="text-sm font-semibold text-slate-200">
              No trade activity yet
            </div>
            <div className="mt-1 text-xs leading-relaxed text-slate-500">
              Entries, take profits, and stop losses will appear here as soon as the bot starts trading.
            </div>
          </div>
        </div>
      ) : (
        <div className="overflow-auto flex-1 min-h-0 pr-1 -mr-1">
          <ul className="flex flex-col gap-1.5">
            <AnimatePresence initial={false}>
              {trades.map((t, idx) => (
                <TradeRow key={`${t.timestamp}-${t.event}-${t.direction}-${idx}`} trade={t} newest={idx === 0} />
              ))}
            </AnimatePresence>
          </ul>
        </div>
      )}
    </div>
  );
}

function TradeRow({ trade: t, newest }: { trade: TradeEvent; newest: boolean }) {
  const pnlColor =
    t.pnl == null
      ? "text-slate-400"
      : t.pnl > 0
        ? "text-emerald-300"
        : t.pnl < 0
          ? "text-rose-300"
          : "text-slate-300";
  const dirCls = dirColor(t.direction);
  const hasPrices = t.entry_price != null || t.exit_price != null;

  return (
    <motion.li
      initial={newest ? { opacity: 0, y: -8, backgroundColor: bgFor(t.event) } : false}
      animate={{ opacity: 1, y: 0, backgroundColor: "rgba(0,0,0,0)" }}
      transition={{ duration: 1.6 }}
      className="rounded-md border border-ink-800/70 px-2 py-1 font-mono"
    >
      <div className="flex items-center justify-between gap-2 text-[11px]">
        <span className="text-slate-400">{fmtLocalHMS(t.timestamp)}</span>
        <span className="text-slate-200 uppercase tracking-wider text-[10px]">
          {t.event}
        </span>
        <span className={`${dirCls} text-[10px] uppercase`}>
          {t.direction ?? "—"}
        </span>
      </div>
      <div className="flex items-center justify-between gap-2 text-[11px] mt-0.5">
        <span className="text-slate-500">
          {hasPrices
            ? `${fmtPrice(t.entry_price)} → ${fmtPrice(t.exit_price)}`
            : "—"}
        </span>
        <span className={pnlColor}>
          {fmtMoney(t.pnl)}{" "}
          <span className="text-[10px] opacity-80">{fmtPct(t.pnl_pct)}</span>
        </span>
      </div>
    </motion.li>
  );
}

function fmtPrice(v: number | null | undefined): string {
  return v != null ? v.toFixed(4) : "—";
}

function bgFor(event: string): string {
  if (event === "ENTRY") return "rgba(34,211,238,0.18)";
  if (event === "TP_FILLED" || event === "WIN_EXPIRY")
    return "rgba(52,211,153,0.22)";
  if (event === "STOP_LOSS" || event === "LOSS_EXPIRY")
    return "rgba(251,113,133,0.22)";
  return "rgba(148,163,184,0.12)";
}

function dirColor(d?: string | null): string {
  if (d === "UP") return "text-emerald-300";
  if (d === "DOWN") return "text-rose-300";
  return "text-slate-400";
}
