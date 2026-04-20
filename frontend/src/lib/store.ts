import { create } from "zustand";
import type {
  BootstrapPayload,
  CalibrationStatus,
  ChartMarker,
  EdgeRatio,
  InstanceStats,
  LeaderboardRow,
  LivenessInfo,
  PolymarketPrices,
  PositionState,
  PricePoint,
  SharedConfig,
  TerminalSnapshot,
  TradeEvent,
  WindowState,
  WsEnvelope,
} from "./types";

type WsStatus = "connecting" | "open" | "closed";

interface FlashEvent {
  id: string;
  kind: "entry" | "win" | "loss";
  direction?: "UP" | "DOWN";
  amount?: number | null;
  at: number;
}

interface DashState {
  mode: string;
  selectedInstanceId: number;
  instance: InstanceStats | null;
  position: PositionState;
  terminal: TerminalSnapshot | null;
  window: WindowState | null;
  trades: TradeEvent[];
  equity: number[];
  leaderboard: LeaderboardRow[];
  allInstances: LeaderboardRow[];
  liveness: LivenessInfo | null;
  calibration: CalibrationStatus;
  edgeUp: EdgeRatio | null;
  edgeDown: EdgeRatio | null;
  sharedConfig: SharedConfig;
  seriesUp: PricePoint[];
  seriesDown: PricePoint[];
  modelUp: PricePoint[];
  modelDown: PricePoint[];
  markers: ChartMarker[];
  windowStartIso: string | null;
  windowEndIso: string | null;
  equitySeries: PricePoint[];
  wsStatus: WsStatus;
  flashQueue: FlashEvent[];

  setSelected: (id: number) => void;
  setAllInstances: (rows: LeaderboardRow[]) => void;
  setWsStatus: (s: WsStatus) => void;
  applyBootstrap: (p: BootstrapPayload) => void;
  applyEnvelope: (env: WsEnvelope) => void;
  consumeFlash: (id: string) => void;
}

const initialCalibration: CalibrationStatus = {
  active: false,
  started_at: null,
  elapsed_s: null,
  last_timing: null,
};

const CLOSE_EVENTS = new Set([
  "TP_FILLED",
  "WIN_EXPIRY",
  "LOSS_EXPIRY",
  "STOP_LOSS",
  "UNRESOLVED_RESTART",
]);

export const useDash = create<DashState>((set, get) => ({
  mode: "dry_run",
  selectedInstanceId: 100,
  instance: null,
  position: { open: null },
  terminal: null,
  window: null,
  trades: [],
  equity: [],
  leaderboard: [],
  allInstances: [],
  liveness: null,
  calibration: initialCalibration,
  edgeUp: null,
  edgeDown: null,
  seriesUp: [],
  seriesDown: [],
  modelUp: [],
  modelDown: [],
  markers: [],
  windowStartIso: null,
  windowEndIso: null,
  equitySeries: [],
  sharedConfig: {
    starting_capital: null,
    order_size_pct: null,
    friction_pct: null,
    max_entry_price: null,
    no_trade_first_s: null,
    no_trade_last_s: null,
    grace_period_s: null,
    liquidity_mode: null,
  },
  wsStatus: "connecting",
  flashQueue: [],

  setSelected: (id) => set({ selectedInstanceId: id }),
  setAllInstances: (rows) => set({ allInstances: rows }),
  setWsStatus: (s) => set({ wsStatus: s }),

  applyBootstrap: (p) =>
    set({
      mode: p.mode,
      instance: p.instance,
      position: p.position,
      terminal: p.terminal,
      window: p.window,
      trades: p.trades,
      equity: p.equity,
      leaderboard: p.leaderboard_top,
      liveness: p.liveness,
      calibration: p.calibration ?? initialCalibration,
      edgeUp: p.edge_up,
      edgeDown: p.edge_down,
      sharedConfig: p.shared_config ?? get().sharedConfig,
      seriesUp: p.series_up ?? [],
      seriesDown: p.series_down ?? [],
      modelUp: p.model_up ?? [],
      modelDown: p.model_down ?? [],
      markers: p.markers ?? [],
      windowStartIso: p.window_start_iso ?? null,
      windowEndIso: p.window_end_iso ?? null,
      equitySeries: p.equity_series ?? [],
    }),

  applyEnvelope: (env) => {
    switch (env.type) {
      case "bootstrap":
        get().applyBootstrap(env.data);
        break;
      case "terminal.update": {
        const incoming = env.data;
        const prev = get().terminal;
        const polymarket =
          incoming.polymarket?.prob_up != null
            ? incoming.polymarket
            : (prev?.polymarket ?? incoming.polymarket);
        const market =
          incoming.market?.slug
            ? incoming.market
            : { ...incoming.market, slug: prev?.market?.slug ?? incoming.market?.slug };
        set((st) => {
          const patch = ensureSlug(st, market?.slug ?? null);
          return { ...patch, terminal: { ...incoming, polymarket, market } };
        });
        recomputeEdge(get, set);
        break;
      }
      case "orderbook.update": {
        const prices = env.data.prices;
        const incomingUp = env.data.series_up ?? null;
        const incomingDown = env.data.series_down ?? null;
        set((st) => ({
          terminal:
            st.terminal && prices
              ? { ...st.terminal, polymarket: prices }
              : st.terminal,
          seriesUp: incomingUp ?? st.seriesUp,
          seriesDown: incomingDown ?? st.seriesDown,
        }));
        recomputeEdge(get, set);
        break;
      }
      case "model.update": {
        const incomingUp = env.data.series_up ?? null;
        const incomingDown = env.data.series_down ?? null;
        set((st) => ({
          modelUp: incomingUp ?? st.modelUp,
          modelDown: incomingDown ?? st.modelDown,
        }));
        break;
      }
      case "instance.update":
        set({
          instance: env.data.instance,
          position: env.data.position,
          equity: env.data.equity,
          equitySeries: env.data.equity_series ?? get().equitySeries,
        });
        break;
      case "window.tick": {
        const win = env.data;
        const bounds = windowBoundsFromSlug(win.slug);
        set((st) => {
          const patch = ensureSlug(st, win.slug ?? null);
          return {
            ...patch,
            window: win,
            windowStartIso: bounds?.startIso ?? st.windowStartIso,
            windowEndIso: bounds?.endIso ?? st.windowEndIso,
          };
        });
        break;
      }
      case "liveness.update":
      case "liveness.tick":
        set({ liveness: env.data });
        break;
      case "leaderboard.update":
        set({ leaderboard: env.data.top });
        break;
      case "calibration.start":
      case "calibration.end":
        set({ calibration: env.data });
        break;
      case "trade.append":
        handleTrade(env.data, get, set);
        break;
      default:
        break;
    }
  },

  consumeFlash: (id) =>
    set((st) => ({ flashQueue: st.flashQueue.filter((f) => f.id !== id) })),
}));

/**
 * Slug transition handler.
 *
 * The PriceChart filters points and markers by window bounds (derived from slug)
 * at render time, so we don't need to clear stored series aggressively here —
 * doing so was causing "blank" moments when a fresh `orderbook.update` had
 * already arrived before the next `model.update`.
 *
 * The backend collectors each own a slug_fn and reset their own internal deques
 * on boundary, so the data streaming into the store is already scoped. This
 * function is now a no-op kept only for a potential future hook point.
 */
function ensureSlug(
  _st: DashState,
  _newSlug: string | null,
): Partial<DashState> {
  return {};
}

function windowBoundsFromSlug(slug: string | null | undefined): {
  startIso: string;
  endIso: string;
} | null {
  if (!slug) return null;
  const m = /btc-updown-15m-(\d+)/.exec(slug);
  if (!m) return null;
  const start = Number(m[1]) * 1000; // ms since epoch
  const end = start + 900_000;
  return {
    startIso: new Date(start).toISOString(),
    endIso: new Date(end).toISOString(),
  };
}

function recomputeEdge(
  get: () => DashState,
  set: (partial: Partial<DashState>) => void,
) {
  const st = get();
  const params = st.instance?.params;
  if (!params || !st.terminal) return;
  const poly = st.terminal.polymarket;
  const probs = st.terminal.probabilities;
  const modelUp =
    probs.avg_above ?? probs.mc_above ?? probs.ssvi_surface_above ?? null;
  const modelDown =
    probs.avg_below ?? probs.mc_below ?? probs.ssvi_surface_below ?? null;
  set({
    edgeUp: computeEdge("UP", modelUp, poly.prob_up, params.alpha_up, params.floor_up),
    edgeDown: computeEdge(
      "DOWN",
      modelDown,
      poly.prob_down,
      params.alpha_down,
      params.floor_down,
    ),
  });
}

function computeEdge(
  side: "UP" | "DOWN",
  model: number | null,
  market: number | null,
  alpha: number,
  floor: number,
): EdgeRatio {
  if (market == null) {
    return {
      side,
      market_prob: null,
      model_prob: model,
      required_prob: null,
      current_ratio: null,
      required_ratio: null,
      margin: null,
      has_edge: null,
    };
  }
  const required = Math.max(floor, 1 - Math.pow(1 - market, alpha));
  const currentRatio = model != null && market > 0 ? model / market : null;
  const requiredRatio = market > 0 ? required / market : null;
  const margin =
    currentRatio != null && requiredRatio != null
      ? currentRatio - requiredRatio
      : null;
  return {
    side,
    market_prob: market,
    model_prob: model,
    required_prob: required,
    current_ratio: currentRatio,
    required_ratio: requiredRatio,
    margin,
    has_edge: model != null ? model >= required : null,
  };
}

function handleTrade(
  ev: TradeEvent,
  get: () => DashState,
  set: (partial: Partial<DashState>) => void,
) {
  if (ev.instance_id !== get().selectedInstanceId) return;
  const st = get();
  const trades = [ev, ...st.trades].slice(0, 200);
  const flashQueue = [...st.flashQueue];
  const position = nextPositionState(st, ev);
  const marketContext = nextMarketContext(st, ev);
  const chartContext = nextEntryChartContext(st, ev);
  const activeSlug =
    marketContext.terminal?.market?.slug ?? st.terminal?.market?.slug;
  const eKind = classifyEvent(ev.event);
  if (eKind) {
    flashQueue.push({
      id: `${ev.timestamp}-${ev.event}-${ev.instance_id}`,
      kind: eKind,
      direction: (ev.direction as "UP" | "DOWN" | undefined) ?? undefined,
      amount: ev.pnl ?? null,
      at: Date.now(),
    });
  }
  // Also add to the price-chart marker layer if the event belongs to the current market.
  const markerKind: ChartMarker["kind"] | null =
    ev.event === "ENTRY"
      ? "ENTRY"
      : ev.event === "TP_FILLED" || ev.event === "WIN_EXPIRY"
        ? "WIN"
        : ev.event === "STOP_LOSS" || ev.event === "LOSS_EXPIRY"
          ? "LOSS"
          : null;
  let markers = st.markers;
  if (markerKind) {
    if (!activeSlug || !ev.market_id || ev.market_id === activeSlug) {
      markers = [
        ...markers,
        {
          t: ev.timestamp,
          kind: markerKind,
          side: (ev.direction as "UP" | "DOWN" | null | undefined) ?? null,
          price: markerKind === "ENTRY" ? ev.entry_price ?? null : ev.exit_price ?? null,
          pnl: ev.pnl ?? null,
        },
      ].slice(-60);
    }
  }

  const liveEquity = nextLiveEquity(st, ev);
  set({
    trades,
    flashQueue,
    markers,
    position,
    ...marketContext,
    ...chartContext,
    ...liveEquity,
  });
}

function classifyEvent(
  eventName: string,
): "entry" | "win" | "loss" | null {
  if (eventName === "ENTRY") return "entry";
  if (eventName === "TP_FILLED" || eventName === "WIN_EXPIRY") return "win";
  if (eventName === "STOP_LOSS" || eventName === "LOSS_EXPIRY") return "loss";
  return null;
}

function nextLiveEquity(
  st: DashState,
  ev: TradeEvent,
): Partial<DashState> {
  if (!CLOSE_EVENTS.has(ev.event)) return {};

  const start =
    st.instance?.starting_capital ?? st.sharedConfig.starting_capital ?? 1000;
  const lastEquity =
    st.equity.length > 0 ? st.equity[st.equity.length - 1] : start;
  const nextEquity =
    ev.capital ?? (ev.pnl != null ? lastEquity + ev.pnl : null);
  if (nextEquity == null) return {};

  const equity = [...st.equity, nextEquity];
  const equitySeries =
    st.equitySeries.length === 0
      ? [
          { t: ev.timestamp, v: start },
          { t: ev.timestamp, v: nextEquity },
        ]
      : [...st.equitySeries, { t: ev.timestamp, v: nextEquity }];

  return { equity, equitySeries };
}

function nextPositionState(st: DashState, ev: TradeEvent): PositionState {
  if (
    ev.event === "ENTRY" &&
    ev.entry_price != null &&
    ev.shares != null &&
    (ev.direction === "UP" || ev.direction === "DOWN")
  ) {
    const tpPct = st.instance?.params?.tp_pct ?? null;
    const slPct = st.instance?.params?.sl_pct ?? null;
    const tpTarget =
      tpPct != null ? clampProb(ev.entry_price * (1 + tpPct)) : null;
    const slTarget =
      slPct != null && slPct > 0
        ? clampProb(ev.entry_price * (1 - slPct))
        : null;
    return {
      ...st.position,
      open: {
        direction: ev.direction,
        entry_price: ev.entry_price,
        shares: ev.shares,
        tp_target: tpTarget,
        sl_target: slTarget,
        entered_at: ev.timestamp,
        market_id: ev.market_id ?? null,
        notional: ev.entry_price * ev.shares,
      },
    };
  }

  if (CLOSE_EVENTS.has(ev.event)) {
    return {
      ...st.position,
      open: null,
      last_exit_at: ev.timestamp,
    };
  }

  return st.position;
}

function nextMarketContext(
  st: DashState,
  ev: TradeEvent,
): Partial<DashState> {
  if (ev.event !== "ENTRY" || !ev.market_id) return {};
  const currentSlug = st.terminal?.market?.slug ?? st.window?.slug ?? null;
  if (currentSlug === ev.market_id) return {};

  const bounds = windowBoundsFromSlug(ev.market_id);
  return {
    terminal: st.terminal
      ? {
          ...st.terminal,
          market: { ...st.terminal.market, slug: ev.market_id },
        }
      : st.terminal,
    window: st.window ? { ...st.window, slug: ev.market_id } : st.window,
    windowStartIso: bounds?.startIso ?? st.windowStartIso,
    windowEndIso: bounds?.endIso ?? st.windowEndIso,
  };
}

function clampProb(v: number): number {
  return Math.max(0, Math.min(1, v));
}

function nextEntryChartContext(
  st: DashState,
  ev: TradeEvent,
): Partial<DashState> {
  if (
    ev.event !== "ENTRY" ||
    ev.timestamp == null ||
    ev.model_prob == null ||
    (ev.direction !== "UP" && ev.direction !== "DOWN")
  ) {
    return {};
  }

  const modelProb = clampProb(ev.model_prob);
  const modelPatch =
    ev.direction === "UP"
      ? {
          modelUp: appendPoint(st.modelUp, ev.timestamp, modelProb),
          modelDown: appendPoint(st.modelDown, ev.timestamp, clampProb(1 - modelProb)),
        }
      : {
          modelUp: appendPoint(st.modelUp, ev.timestamp, clampProb(1 - modelProb)),
          modelDown: appendPoint(st.modelDown, ev.timestamp, modelProb),
        };

  return modelPatch;
}

function appendPoint(
  series: PricePoint[],
  t: string,
  v: number,
): PricePoint[] {
  const next = [...series];
  const last = next[next.length - 1];
  if (last && last.t === t) {
    next[next.length - 1] = { t, v };
    return next;
  }
  next.push({ t, v });
  return next;
}
