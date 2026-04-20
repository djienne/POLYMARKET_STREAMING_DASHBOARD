import { AnimatePresence, motion } from "framer-motion";
import { useDash } from "../lib/store";
import { fmtLocalHMS, fmtMoney, fmtPct } from "../lib/format";

export default function TradeFeed() {
  const trades = useDash((s) => s.trades);

  return (
    <div className="card p-4 h-full flex flex-col">
      <div className="flex items-baseline justify-between mb-2">
        <h2 className="card-header">Trade feed</h2>
        <span className="text-[11px] text-slate-500 font-mono">
          last {trades.length}
        </span>
      </div>

      <div className="overflow-auto flex-1 min-h-0 pr-1">
        <table className="w-full text-[11px] font-mono">
          <thead className="text-slate-500 text-[10px] uppercase tracking-widest sticky top-0 bg-ink-900/90 backdrop-blur">
            <tr>
              <th className="text-left py-1">time</th>
              <th className="text-left">event</th>
              <th className="text-left">dir</th>
              <th className="text-right">entry</th>
              <th className="text-right">exit</th>
              <th className="text-right">pnl</th>
              <th className="text-right">%</th>
            </tr>
          </thead>
          <tbody>
            <AnimatePresence initial={false}>
              {trades.map((t, idx) => {
                const pnlColor =
                  t.pnl == null
                    ? "text-slate-400"
                    : t.pnl > 0
                      ? "text-emerald-300"
                      : t.pnl < 0
                        ? "text-rose-300"
                        : "text-slate-300";
                const newest = idx === 0;
                return (
                  <motion.tr
                    key={`${t.timestamp}-${t.event}-${t.direction}-${idx}`}
                    initial={newest ? { opacity: 0, y: -10, backgroundColor: bgFor(t.event) } : false}
                    animate={{ opacity: 1, y: 0, backgroundColor: "rgba(0,0,0,0)" }}
                    transition={{ duration: 1.6 }}
                    className="border-t border-ink-800/60"
                  >
                    <td className="py-1 text-slate-400">
                      {fmtLocalHMS(t.timestamp)}
                    </td>
                    <td className="text-slate-200">{t.event}</td>
                    <td className={dirColor(t.direction)}>{t.direction ?? "—"}</td>
                    <td className="text-right text-slate-200">
                      {t.entry_price != null ? t.entry_price.toFixed(4) : "—"}
                    </td>
                    <td className="text-right text-slate-200">
                      {t.exit_price != null ? t.exit_price.toFixed(4) : "—"}
                    </td>
                    <td className={`text-right ${pnlColor}`}>
                      {fmtMoney(t.pnl)}
                    </td>
                    <td className={`text-right ${pnlColor}`}>
                      {fmtPct(t.pnl_pct)}
                    </td>
                  </motion.tr>
                );
              })}
            </AnimatePresence>
            {trades.length === 0 && (
              <tr>
                <td colSpan={7} className="py-6 text-center text-slate-500">
                  No trades yet for this instance
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
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
