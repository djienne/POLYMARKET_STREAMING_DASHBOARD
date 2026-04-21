import { useMemo } from "react";
import { useDash } from "../lib/store";
import { fmtLocalDate, fmtMoney, fmtPct, parisDateKey } from "../lib/format";
import { CLOSE_EVENTS } from "../lib/trade-derive";

const WIN_EVENTS = new Set(["TP_FILLED", "WIN_EXPIRY"]);
const LOSS_EVENTS = new Set(["STOP_LOSS", "LOSS_EXPIRY"]);

export default function InstanceStatsCard() {
  const inst = useDash((s) => s.instance);
  const shared = useDash((s) => s.sharedConfig);
  const trades = useDash((s) => s.trades);
  const equitySeries = useDash((s) => s.equitySeries);
  const params = inst?.params;

  const { firstTs, daysLive, cagrDisplay, cagrPositive } = useMemo(() => {
    const candidates: number[] = [];
    if (equitySeries.length > 0) {
      const t = new Date(equitySeries[0].t).getTime();
      if (Number.isFinite(t)) candidates.push(t);
    }
    if (trades.length > 0) {
      const t = new Date(trades[trades.length - 1].timestamp).getTime();
      if (Number.isFinite(t)) candidates.push(t);
    }
    const first = candidates.length > 0 ? Math.min(...candidates) : null;
    if (first == null || !inst) {
      return { firstTs: null, daysLive: null, cagrDisplay: "—", cagrPositive: true };
    }
    const days = Math.max(0, (Date.now() - first) / 86_400_000);
    const start = inst.starting_capital;
    const capital = inst.capital;
    if (days < 1 || start <= 0 || !Number.isFinite(capital) || capital <= 0) {
      return { firstTs: first, daysLive: days, cagrDisplay: "—", cagrPositive: true };
    }
    const years = days / 365;
    const totalReturn = capital / start;
    const cagr = Math.pow(totalReturn, 1 / years) - 1;
    if (!Number.isFinite(cagr)) {
      return { firstTs: first, daysLive: days, cagrDisplay: "—", cagrPositive: true };
    }
    const pct = cagr * 100;
    const display =
      pct > 1000 ? ">1000%" : pct < -1000 ? "<-1000%" : fmtPct(pct, 1);
    return {
      firstTs: first,
      daysLive: days,
      cagrDisplay: display,
      cagrPositive: pct >= 0,
    };
  }, [trades, equitySeries, inst]);

  const today = useMemo(() => {
    const empty = { pnl: 0, pnlPct: null as number | null, entries: 0, wins: 0, losses: 0, closed: 0 };
    if (trades.length === 0) return empty;
    const todayKey = parisDateKey(Date.now());
    let pnl = 0;
    let entries = 0;
    let wins = 0;
    let losses = 0;
    let closed = 0;
    for (const t of trades) {
      if (parisDateKey(t.timestamp) !== todayKey) continue;
      if (t.event === "ENTRY") entries += 1;
      if (CLOSE_EVENTS.has(t.event)) {
        if (t.pnl != null) pnl += t.pnl;
        if (WIN_EVENTS.has(t.event)) wins += 1;
        else if (LOSS_EVENTS.has(t.event)) losses += 1;
        closed += 1;
      }
    }
    // Portfolio-level %: PnL $ relative to capital at the last equity point
    // strictly before today's local midnight. Fall back to starting_capital,
    // then to (current capital − today's PnL) if equity history is sparse.
    let baseCapital: number | null = null;
    if (equitySeries.length > 0) {
      for (let i = equitySeries.length - 1; i >= 0; i--) {
        const p = equitySeries[i];
        if (parisDateKey(p.t) !== todayKey) {
          baseCapital = p.v;
          break;
        }
      }
    }
    if (baseCapital == null && inst) {
      const fallback = inst.capital - pnl;
      baseCapital = fallback > 0 ? fallback : inst.starting_capital;
    }
    const pnlPct =
      baseCapital && baseCapital > 0 && closed > 0
        ? (pnl / baseCapital) * 100
        : null;
    return { pnl, pnlPct, entries, wins, losses, closed };
  }, [trades, equitySeries, inst]);

  if (!inst) {
    return <div className="card p-5 text-slate-500 text-sm">Loading…</div>;
  }

  const tiles = [
    {
      label: "Capital",
      value: `$${inst.capital.toFixed(2)}`,
      sub: `start $${inst.starting_capital.toFixed(0)}`,
    },
    {
      label: "Total PnL",
      value: fmtMoney(inst.total_pnl),
      sub: fmtPct(inst.total_pnl_pct),
      color: inst.total_pnl >= 0 ? "text-emerald-300" : "text-rose-300",
    },
    {
      label: "Sharpe",
      value: inst.sharpe.toFixed(2),
      color: inst.sharpe >= 1 ? "text-emerald-300" : "text-slate-100",
    },
    {
      label: "Max DD",
      value: `${inst.max_drawdown_pct.toFixed(2)}%`,
      sub: `$${inst.max_drawdown.toFixed(2)}`,
      color: "text-amber-300",
    },
    {
      label: "Win rate",
      value: `${inst.win_rate.toFixed(1)}%`,
      sub: `${inst.wins}W / ${inst.losses}L`,
    },
    {
      label: "Trades",
      value: String(inst.trades_count),
      sub: "",
    },
    {
      label: "Days",
      value: daysLive != null ? `${Math.floor(daysLive)}d` : "—",
      sub: firstTs != null ? `since ${fmtLocalDate(firstTs)}` : "",
    },
    {
      label: "CAGR",
      value: cagrDisplay,
      sub: "annualized",
      color:
        cagrDisplay === "—"
          ? "text-slate-100"
          : cagrPositive
            ? "text-emerald-300"
            : "text-rose-300",
    },
  ];

  const todayClosed = today.wins + today.losses;
  const todayWinRate = todayClosed > 0 ? (today.wins / todayClosed) * 100 : null;
  const todayTiles = [
    {
      label: "PnL $",
      value: today.closed > 0 ? fmtMoney(today.pnl) : "—",
      color: today.pnl > 0 ? "text-emerald-300" : today.pnl < 0 ? "text-rose-300" : "text-slate-100",
    },
    {
      label: "PnL %",
      value: today.pnlPct != null ? fmtPct(today.pnlPct) : "—",
      color:
        today.pnlPct == null
          ? "text-slate-100"
          : today.pnlPct > 0
            ? "text-emerald-300"
            : today.pnlPct < 0
              ? "text-rose-300"
              : "text-slate-100",
    },
    {
      label: "Positions",
      value: String(today.entries),
      sub: today.closed > 0 ? `${today.closed} closed` : "",
    },
    {
      label: "Win rate",
      value: todayWinRate != null ? `${todayWinRate.toFixed(0)}%` : "—",
      sub: todayClosed > 0 ? `${today.wins}W / ${today.losses}L` : "",
    },
  ];

  // Per-trade order size estimate based on current capital * order_size_pct
  const orderSizePct = shared.order_size_pct ?? null;
  const orderSizeUsd =
    orderSizePct != null ? inst.capital * orderSizePct : null;

  const paramTiles: ParamTile[] = params
    ? [
        {
          short: "aU",
          long: "alpha up",
          value: params.alpha_up.toFixed(1),
          hint: "tail exponent (UP side)",
        },
        {
          short: "aD",
          long: "alpha down",
          value: params.alpha_down.toFixed(1),
          hint: "tail exponent (DOWN side)",
        },
        {
          short: "fU",
          long: "floor up",
          value: params.floor_up.toFixed(2),
          hint: "min required prob to enter UP",
        },
        {
          short: "fD",
          long: "floor down",
          value: params.floor_down.toFixed(2),
          hint: "min required prob to enter DOWN",
        },
        {
          short: "tp",
          long: "take profit",
          value: (params.tp_pct * 100).toFixed(0) + "%",
          hint: "exit target on entry price",
        },
        {
          short: "sl",
          long: "stop loss",
          value:
            params.sl_pct > 0
              ? (params.sl_pct * 100).toFixed(0) + "%"
              : "off",
          hint: "hard stop (off when 0)",
          muted: params.sl_pct === 0,
        },
      ]
    : [];

  return (
    <div className="card p-4 h-full flex flex-col overflow-hidden">
      <div className="mb-2">
        <h2 className="card-header">Performance</h2>
        {orderSizePct != null && (
          <div className="text-[10px] text-slate-500 font-mono mt-0.5">
            size{" "}
            <span className="text-cyan-200">
              {(orderSizePct * 100).toFixed(1)}%
            </span>
            {orderSizeUsd != null && (
              <span className="text-slate-400">
                {" (≈ $"}
                {orderSizeUsd.toFixed(2)}
                {"/trade)"}
              </span>
            )}
            {shared.friction_pct != null && (
              <span> · friction {(shared.friction_pct * 100).toFixed(2)}%</span>
            )}
            {shared.max_entry_price != null && (
              <span> · max entry {shared.max_entry_price.toFixed(2)}</span>
            )}
          </div>
        )}
      </div>

      <div className="grid grid-cols-8 gap-2 mb-2">
        {tiles.map((t) => (
          <div key={t.label}>
            <div className="stat-label">{t.label}</div>
            <div className={`font-mono text-base ${t.color ?? "text-slate-100"}`}>
              {t.value}
            </div>
            {t.sub && (
              <div className="text-[10px] text-slate-500 font-mono">
                {t.sub}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="mb-2">
        <div className="stat-label mb-1">Today</div>
        <div className="grid grid-cols-4 gap-2">
          {todayTiles.map((t) => (
            <div key={t.label}>
              <div className="text-[10px] uppercase tracking-wider text-slate-500">
                {t.label}
              </div>
              <div className={`font-mono text-base ${t.color ?? "text-slate-100"}`}>
                {t.value}
              </div>
              {t.sub && (
                <div className="text-[10px] text-slate-500 font-mono">
                  {t.sub}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {params && (
        <div className="grid grid-cols-6 gap-2">
          {paramTiles.map((p) => (
            <ParamChip key={p.short} tile={p} />
          ))}
        </div>
      )}
    </div>
  );
}

type ParamTile = {
  short: string;
  long: string;
  value: string;
  hint: string;
  muted?: boolean;
};

function ParamChip({ tile }: { tile: ParamTile }) {
  return (
    <div
      title={tile.hint}
      className={`rounded-md border border-ink-800 bg-ink-900/40 px-2 py-1.5 ${
        tile.muted ? "opacity-60" : ""
      }`}
    >
      <div className="flex items-baseline gap-1.5">
        <span className="font-mono text-cyan-200 text-xs">
          {tile.short}
        </span>
        <span className="text-[10px] text-slate-500 uppercase tracking-wider">
          {tile.long}
        </span>
      </div>
      <div
        className={`font-mono text-base ${
          tile.muted ? "text-slate-500" : "text-slate-100"
        }`}
      >
        {tile.value}
      </div>
    </div>
  );
}
