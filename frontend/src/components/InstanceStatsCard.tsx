import { useDash } from "../lib/store";
import { fmtMoney, fmtPct } from "../lib/format";

export default function InstanceStatsCard() {
  const inst = useDash((s) => s.instance);
  const shared = useDash((s) => s.sharedConfig);
  const params = inst?.params;

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
      value: `$${inst.max_drawdown.toFixed(2)}`,
      sub: `${inst.max_drawdown_pct.toFixed(2)}%`,
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

      <div className="grid grid-cols-6 gap-2 mb-2">
        {tiles.map((t) => (
          <div key={t.label}>
            <div className="stat-label">{t.label}</div>
            <div className={`font-mono text-lg ${t.color ?? "text-slate-100"}`}>
              {t.value}
            </div>
            {t.sub && (
              <div className="text-[11px] text-slate-500 font-mono">
                {t.sub}
              </div>
            )}
          </div>
        ))}
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
