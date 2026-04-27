import { useMemo } from "react";
import { useDash } from "../lib/store";
import { fmtMoney, fmtPct } from "../lib/format";

export default function InstanceStatsCard() {
  const inst = useDash((s) => s.instance);
  const shared = useDash((s) => s.sharedConfig);
  const trades = useDash((s) => s.trades);
  const equitySeries = useDash((s) => s.equitySeries);
  const today = useDash((s) => s.todaySummary);
  const mode = useDash((s) => s.mode);

  // Realized-only capital: ignores whatever notional is locked into the
  // currently-open position, so the ALL TIME section doesn't dip while a
  // trade is in-flight. `equitySeries` only grows on CLOSE_EVENTS (see
  // trade-derive.ts nextLiveEquity), so its last value IS the realized
  // capital; if nothing has closed yet we fall back to starting capital.
  const realizedCapital =
    equitySeries.length > 0
      ? equitySeries[equitySeries.length - 1].v
      : inst?.starting_capital ?? shared.starting_capital ?? 0;

  const cagrUnavailable = "--";
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
      return {
        firstTs: null,
        daysLive: null,
        cagrDisplay: cagrUnavailable,
        cagrPositive: true,
      };
    }
    const days = Math.max(0, (Date.now() - first) / 86_400_000);
    const start = inst.starting_capital;
    const capital = realizedCapital;
    if (days < 1 || start <= 0 || !Number.isFinite(capital) || capital <= 0) {
      return {
        firstTs: first,
        daysLive: days,
        cagrDisplay: cagrUnavailable,
        cagrPositive: true,
      };
    }
    const years = days / 365;
    const totalReturn = capital / start;
    const cagr = Math.pow(totalReturn, 1 / years) - 1;
    if (!Number.isFinite(cagr)) {
      return {
        firstTs: first,
        daysLive: days,
        cagrDisplay: cagrUnavailable,
        cagrPositive: true,
      };
    }
    const pct = cagr * 100;
    if (pct <= -90) {
      return {
        firstTs: first,
        daysLive: days,
        cagrDisplay: cagrUnavailable,
        cagrPositive: true,
      };
    }
    const display =
      pct > 1000 ? ">1000%" : pct < -1000 ? "<-1000%" : fmtPct(pct, 1);
    return {
      firstTs: first,
      daysLive: days,
      cagrDisplay: display,
      cagrPositive: pct >= 0,
    };
  }, [trades, equitySeries, inst, realizedCapital]);

  const startingCapital =
    inst?.starting_capital ?? shared.starting_capital ?? 0;
  const view = inst ?? {
    capital: startingCapital,
    starting_capital: startingCapital,
    total_pnl: 0,
    total_pnl_pct: 0,
    sharpe: 0,
    max_drawdown: 0,
    max_drawdown_pct: 0,
    win_rate: 0,
    wins: 0,
    losses: 0,
    trades_count: 0,
  };
  const hasTrades = view.trades_count > 0;

  // Capital + Total PnL source the on-chain USDC balance the trader fetches
  // from Polygon RPC (state.json.capital.current → inst.capital). That's
  // what Polymarket shows; during an open position it legitimately dips
  // by the cost_basis because USDC is briefly tied up as shares. Earlier
  // commit routed these through equitySeries to hide the dip, but that
  // broke the Polymarket-truth invariant — user sees a $2+ mismatch with
  // the Polymarket UI. CAGR keeps using realizedCapital below so the
  // long-horizon return signal doesn't flicker on every trade.
  const usdcPnl = view.capital - view.starting_capital;
  const usdcPnlPct =
    view.starting_capital > 0
      ? (usdcPnl / view.starting_capital) * 100
      : 0;

  const tiles = [
    {
      label: "Capital",
      value: `$${view.capital.toFixed(2)}`,
      sub: `start $${view.starting_capital.toFixed(2)}`,
    },
    {
      label: "Sharpe",
      value: hasTrades ? view.sharpe.toFixed(2) : "—",
      color:
        !hasTrades
          ? "text-slate-400"
          : view.sharpe >= 1
            ? "text-emerald-300"
            : "text-slate-100",
    },
    {
      label: "Max DD",
      value: `${view.max_drawdown_pct.toFixed(2)}%`,
      sub: `$${view.max_drawdown.toFixed(2)}`,
      color: "text-amber-300",
    },
    {
      label: "Win rate",
      value: hasTrades ? `${view.win_rate.toFixed(1)}%` : "—",
      sub: hasTrades ? `${view.wins}W / ${view.losses}L` : "",
    },
    {
      label: "Trades",
      value: String(view.trades_count),
      sub: "",
    },
    {
      label: "Days",
      value: daysLive != null ? `${daysLive.toFixed(1)}d` : "0.0d",
      sub: `started ${new Date(firstTs ?? Date.now()).toLocaleDateString("en-GB", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
      })}`,
    },
    {
      label: "CAGR",
      value: cagrDisplay,
      sub: "annualized",
      color:
        cagrDisplay === cagrUnavailable
          ? "text-slate-100"
          : cagrPositive
            ? "text-emerald-300"
            : "text-rose-300",
    },
  ];

  const todayClosed = today.wins + today.losses;
  const todayWinRate =
    todayClosed > 0 ? (today.wins / todayClosed) * 100 : null;
  const todayPnlPctColor =
    today.pnl_pct == null
      ? "text-slate-100"
      : today.pnl_pct > 0
        ? "text-emerald-200"
        : today.pnl_pct < 0
          ? "text-rose-200"
          : "text-slate-100";
  const allTimePnlPctColor =
    usdcPnlPct > 0
      ? "text-emerald-200"
      : usdcPnlPct < 0
        ? "text-rose-200"
        : "text-slate-100";
  const headlineTiles = [
    {
      label: "Daily PnL %",
      value: today.pnl_pct != null ? fmtPct(today.pnl_pct) : "--",
      sub:
        today.closed > 0
          ? `${fmtMoney(today.pnl)} today | ${today.closed} closed`
          : `${today.entries} positions today`,
      color: todayPnlPctColor,
      frame:
        today.pnl_pct == null
          ? "border-slate-700/80 bg-slate-900/50"
          : today.pnl_pct >= 0
            ? "border-emerald-400/35 bg-emerald-500/10"
            : "border-rose-400/35 bg-rose-500/10",
    },
    {
      label: "All Time PnL %",
      value: fmtPct(usdcPnlPct),
      sub: `${fmtMoney(usdcPnl)} total | capital $${view.capital.toFixed(2)}`,
      color: allTimePnlPctColor,
      frame:
        usdcPnlPct >= 0
          ? "border-emerald-400/35 bg-emerald-500/10"
          : "border-rose-400/35 bg-rose-500/10",
    },
  ];
  const todayTiles = [
    {
      label: "PnL $",
      value: today.closed > 0 ? fmtMoney(today.pnl) : "—",
      color:
        today.pnl > 0
          ? "text-emerald-300"
          : today.pnl < 0
            ? "text-rose-300"
            : "text-slate-100",
    },
    {
      label: "PnL %",
      value: today.pnl_pct != null ? fmtPct(today.pnl_pct) : "—",
      color:
        today.pnl_pct == null
          ? "text-slate-100"
          : today.pnl_pct > 0
            ? "text-emerald-300"
            : today.pnl_pct < 0
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

  const orderSizePct = shared.order_size_pct ?? null;
  const orderSizeUsd =
    orderSizePct != null ? view.capital * orderSizePct : null;

  return (
    <div className="card p-3 h-full flex flex-col overflow-hidden">
      <div className="mb-1.5">
        <h2 className="card-header">Performance</h2>
        {orderSizePct != null && (
          <div className="text-[10px] leading-tight text-slate-500 font-mono mt-0.5">
            position size{" "}
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
            {mode === "live" && (
              <span>
                {" · "}
                <span
                  className="text-amber-300/80"
                  title="Live parameters are read from the active trader config"
                >
                  live parameter set active
                </span>
              </span>
            )}
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2 mb-2">
        {headlineTiles.map((tile) => (
          <div
            key={tile.label}
            className={`min-h-[78px] rounded-lg border px-3 py-2 ${tile.frame}`}
          >
            <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400">
              {tile.label}
            </div>
            <div
              className={`mt-1 font-mono text-[30px] leading-none ${tile.color}`}
            >
              {tile.value}
            </div>
            <div className="mt-1 truncate text-[10px] font-mono text-slate-400">
              {tile.sub}
            </div>
          </div>
        ))}
      </div>

      <SectionHeader label="All time" tone="slate" />
      <div className="rounded-xl border border-ink-800/70 bg-[linear-gradient(180deg,rgba(15,23,42,0.26),rgba(15,23,42,0.10))] px-2.5 py-2 mb-1.5">
        <div className="grid grid-cols-8 gap-1.5">
          {tiles.map((t) => (
            <div key={t.label}>
              <div className="stat-label">{t.label}</div>
              <div
                className={`font-mono text-[15px] leading-tight ${t.color ?? "text-slate-100"}`}
              >
                {t.value}
              </div>
              {t.sub && (
                <div className="text-[9px] leading-tight text-slate-500 font-mono">
                  {t.sub}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      <SectionHeader label="Today" tone="cyan" />
      <div className="rounded-xl border border-cyan-500/12 bg-[linear-gradient(180deg,rgba(8,145,178,0.08),rgba(15,23,42,0.10))] px-2.5 py-2 mb-1.5">
        <div className="grid grid-cols-4 gap-1.5">
          {todayTiles.map((t) => (
            <div key={t.label}>
              <div className="text-[10px] uppercase tracking-wider text-slate-500">
                {t.label}
              </div>
              <div
                className={`font-mono text-[15px] leading-tight ${t.color ?? "text-slate-100"}`}
              >
                {t.value}
              </div>
              {t.sub && (
                <div className="text-[9px] leading-tight text-slate-500 font-mono">
                  {t.sub}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}

function StrategyBadge({
  alphaUp,
  alphaDown,
}: {
  alphaUp: number;
  alphaDown: number;
}) {
  const aggressive = alphaUp <= 1.3 && alphaDown <= 1.3;
  const label = aggressive ? "aggressive" : "conservative";
  const colorCls = aggressive
    ? "bg-amber-500/15 text-amber-300 border-amber-500/40"
    : "bg-slate-500/15 text-slate-300 border-slate-500/40";
  const tooltip = aggressive
    ? `aU=${alphaUp.toFixed(1)} & aD=${alphaDown.toFixed(1)} both ≤ 1.3 → light edge requirement, frequent entries`
    : `aU=${alphaUp.toFixed(1)} aD=${alphaDown.toFixed(1)} (at least one > 1.3) → strict edge requirement, infrequent entries`;
  return (
    <span
      title={tooltip}
      className={`chip ${colorCls} font-mono uppercase tracking-wider text-[9px] py-0`}
    >
      <span className="text-slate-400/80 lowercase tracking-normal">strategy</span>
      <span>{label}</span>
    </span>
  );
}

function SectionHeader({
  label,
  tone,
}: {
  label: string;
  tone: "slate" | "cyan";
}) {
  const textCls = tone === "cyan" ? "text-cyan-200" : "text-slate-300";
  const dotCls = tone === "cyan" ? "bg-cyan-300" : "bg-slate-400";
  const lineCls = tone === "cyan" ? "bg-cyan-500/30" : "bg-ink-700";
  return (
    <div className="flex items-center gap-2 mb-1 mt-0.5">
      <span className={`inline-block w-1.5 h-1.5 rounded-full ${dotCls}`} />
      <span
        className={`font-semibold uppercase tracking-[0.18em] text-[11px] ${textCls}`}
      >
        {label}
      </span>
      <div className={`flex-1 h-px ${lineCls}`} />
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
      className={`rounded-lg border border-ink-800/80 bg-[linear-gradient(180deg,rgba(15,23,42,0.38),rgba(15,23,42,0.16))] px-2 py-1 ${
        tile.muted ? "opacity-60" : ""
      }`}
    >
      <div className="flex items-baseline gap-1.5">
        <span className="font-mono text-cyan-200 text-[11px] leading-tight">
          {tile.short}
        </span>
        <span className="text-[9px] leading-tight text-slate-500 uppercase tracking-wider">
          {tile.long}
        </span>
      </div>
      <div
        className={`font-mono text-[13px] leading-tight ${
          tile.muted ? "text-slate-500" : "text-slate-100"
        }`}
      >
        {tile.value}
      </div>
    </div>
  );
}
