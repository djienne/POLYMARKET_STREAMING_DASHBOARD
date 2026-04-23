import { create } from "zustand";
import type {
  BootstrapPayload,
  CalibrationStatus,
  ChartMarker,
  EdgeRatio,
  InstanceStats,
  LeaderboardRow,
  LivenessInfo,
  PositionState,
  PricePoint,
  SharedConfig,
  TimingInfo,
  TerminalSnapshot,
  TodaySummary,
  TradeEvent,
  WindowState,
  WsEnvelope,
} from "./types";
import {
  computeWindowStateFromBounds,
  nextEntryChartContext,
  nextFlashQueue,
  nextLiveEquity,
  nextMarkers,
  nextMarketContext,
  nextPositionState,
  windowBoundsFromSlug,
  type FlashEvent,
} from "./trade-derive";

type WsStatus = "connecting" | "open" | "closed";

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
  todaySummary: TodaySummary;
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
  tickWindow: (nowMs?: number) => void;
  consumeFlash: (id: string) => void;
}

const initialCalibration: CalibrationStatus = {
  active: false,
  started_at: null,
  elapsed_s: null,
  last_timing: null,
};

function mergeLivenessInfo(
  prev: LivenessInfo | null | undefined,
  incoming: LivenessInfo | null | undefined,
): LivenessInfo | null {
  if (!incoming) return prev ?? null;
  return {
    ...incoming,
    polymarket_ping_ms:
      incoming.polymarket_ping_ms != null
        ? incoming.polymarket_ping_ms
        : (prev?.polymarket_ping_ms ?? null),
    polymarket_ping_age_s:
      incoming.polymarket_ping_ms != null
        ? incoming.polymarket_ping_age_s
        : (prev?.polymarket_ping_age_s ?? null),
    execution_label:
      incoming.execution_label != null
        ? incoming.execution_label
        : (prev?.execution_label ?? null),
    execution_location:
      incoming.execution_location != null
        ? incoming.execution_location
        : (prev?.execution_location ?? null),
  };
}

function mergeTimingInfo(
  prev: TimingInfo | null | undefined,
  incoming: TimingInfo | null | undefined,
): TimingInfo | null {
  if (!incoming) return prev ?? null;
  return {
    ...incoming,
    used_gap_s:
      incoming.used_gap_s != null ? incoming.used_gap_s : (prev?.used_gap_s ?? null),
    used_source:
      incoming.used_source != null
        ? incoming.used_source
        : (prev?.used_source ?? null),
  };
}

function toPointTs(t: string): number | null {
  const ts = Date.parse(t);
  return Number.isFinite(ts) ? ts : null;
}

function mergePriceSeries(
  prev: PricePoint[],
  incoming: PricePoint[] | null | undefined,
): PricePoint[] {
  if (!incoming || incoming.length === 0) return prev;
  const byTs = new Map<string, number>();
  for (const p of prev) byTs.set(p.t, p.v);
  for (const p of incoming) byTs.set(p.t, p.v);
  return Array.from(byTs.entries())
    .map(([t, v]) => ({ t, v }))
    .sort((a, b) => {
      const aTs = toPointTs(a.t);
      const bTs = toPointTs(b.t);
      if (aTs != null && bTs != null) return aTs - bTs;
      if (aTs != null) return -1;
      if (bTs != null) return 1;
      return a.t.localeCompare(b.t);
    })
    .slice(-1000);
}

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
  todaySummary: {
    pnl: 0,
    pnl_pct: null,
    entries: 0,
    wins: 0,
    losses: 0,
    closed: 0,
  },
  wsStatus: "connecting",
  flashQueue: [],

  setSelected: (id) => set({ selectedInstanceId: id }),
  setAllInstances: (rows) => set({ allInstances: rows }),
  setWsStatus: (s) => set({ wsStatus: s }),

  applyBootstrap: (p) =>
    set((st) => ({
      ...(st.terminal?.market?.slug !== p.terminal?.market?.slug
        ? {
            calibration: p.calibration ?? initialCalibration,
          }
        : {}),
      mode: p.mode,
      instance: p.instance,
      position: p.position,
      terminal:
        p.terminal != null
          ? {
              ...p.terminal,
              timing:
                mergeTimingInfo(
                  st.terminal?.market?.slug === p.terminal?.market?.slug
                    ? st.terminal?.timing
                    : null,
                  p.terminal.timing,
                ) ?? p.terminal.timing,
            }
          : p.terminal,
      window: computeWindowStateFromBounds(
        p.window,
        p.window_start_iso ?? null,
        p.window_end_iso ?? null,
      ),
      trades: p.trades,
      equity: p.equity,
      leaderboard: p.leaderboard_top,
      liveness: mergeLivenessInfo(st.liveness, p.liveness),
      calibration:
        p.terminal?.timing != null
          ? {
              ...((st.terminal?.market?.slug !== p.terminal?.market?.slug
                ? initialCalibration
                : st.calibration) ?? initialCalibration),
              ...(p.calibration ?? initialCalibration),
              last_timing: mergeTimingInfo(
                st.terminal?.market?.slug === p.terminal?.market?.slug
                  ? st.calibration.last_timing
                  : null,
                p.terminal.timing,
              ),
            }
          : (p.calibration ?? initialCalibration),
      edgeUp: p.edge_up,
      edgeDown: p.edge_down,
      sharedConfig: p.shared_config ?? get().sharedConfig,
      todaySummary: p.today_summary ?? get().todaySummary,
      seriesUp: p.series_up ?? [],
      seriesDown: p.series_down ?? [],
      modelUp: p.model_up ?? [],
      modelDown: p.model_down ?? [],
      markers: p.markers ?? [],
      windowStartIso: p.window_start_iso ?? null,
      windowEndIso: p.window_end_iso ?? null,
      equitySeries: p.equity_series ?? [],
    })),

  applyEnvelope: (env) => {
    switch (env.type) {
      case "bootstrap": {
        const incomingId = env.data.instance?.instance_id ?? null;
        if (incomingId != null && incomingId !== get().selectedInstanceId) break;
        get().applyBootstrap(env.data);
        break;
      }
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
        // Also extract model probabilities from the terminal snapshot and append
        // to modelUp/modelDown. terminal.update fires on every SSVI calibration
        // (every 2–11s), whereas `model.update` (from docker log tailing) only
        // publishes on grid log ticks (~60s). Appending here keeps the dashed
        // chart lines in sync with the trader's actual calibration cadence.
        const probs = incoming.probabilities || {};
        const up =
          probs.avg_above ??
          probs.mc_above ??
          probs.ssvi_surface_above ??
          null;
        const down =
          probs.avg_below ??
          probs.mc_below ??
          probs.ssvi_surface_below ??
          null;
        const ts = incoming.timestamp as string | undefined;
        set((st) => {
          const patch = ensureSlug(st, market?.slug ?? null);
          let modelUp = st.modelUp;
          let modelDown = st.modelDown;
          if (ts && (up != null || down != null)) {
            const lastUpTs = modelUp[modelUp.length - 1]?.t;
            const lastDownTs = modelDown[modelDown.length - 1]?.t;
            if (up != null) {
              modelUp =
                ts === lastUpTs
                  ? [...modelUp.slice(0, -1), { t: ts, v: up }]
                  : [...modelUp, { t: ts, v: up }].slice(-1000);
            }
            if (down != null) {
              modelDown =
                ts === lastDownTs
                  ? [...modelDown.slice(0, -1), { t: ts, v: down }]
                  : [...modelDown, { t: ts, v: down }].slice(-1000);
            }
          }
          const sameMarket = st.terminal?.market?.slug === (market?.slug ?? null);
          const calibration =
            incoming.timing != null
              ? {
                  ...(sameMarket ? st.calibration : initialCalibration),
                  last_timing: mergeTimingInfo(
                    sameMarket ? st.calibration.last_timing : null,
                    incoming.timing,
                  ),
                }
              : (sameMarket ? st.calibration : initialCalibration);
          const timing = mergeTimingInfo(
            sameMarket ? st.terminal?.timing : null,
            incoming.timing,
          );
          return {
            ...patch,
            terminal: {
              ...incoming,
              polymarket,
              market,
              timing: timing ?? incoming.timing,
            },
            calibration,
            modelUp,
            modelDown,
          };
        });
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
          // Both the direct CLOB poller and the CSV fallback can publish this
          // topic. Merge by timestamp so a shorter/staler update never makes
          // the chart "snap back" to a smoother-looking sparse series.
          seriesUp: mergePriceSeries(st.seriesUp, incomingUp),
          seriesDown: mergePriceSeries(st.seriesDown, incomingDown),
        }));
        break;
      }
      case "edge.update":
        set({ edgeUp: env.data.edge_up, edgeDown: env.data.edge_down });
        break;
      case "model.update": {
        const incomingUp = env.data.series_up ?? null;
        const incomingDown = env.data.series_down ?? null;
        set((st) => ({
          modelUp: mergePriceSeries(st.modelUp, incomingUp),
          modelDown: mergePriceSeries(st.modelDown, incomingDown),
        }));
        break;
      }
      case "instance.update":
        set({
          instance: env.data.instance,
          position: env.data.position,
          equity: env.data.equity,
          equitySeries: env.data.equity_series ?? get().equitySeries,
          todaySummary: env.data.today_summary ?? get().todaySummary,
        });
        break;
      case "window.tick": {
        const win = env.data;
        const bounds = windowBoundsFromSlug(win.slug);
        set((st) => {
          const patch = ensureSlug(st, win.slug ?? null);
          return {
            ...patch,
            window: computeWindowStateFromBounds(
              win,
              bounds?.startIso ?? st.windowStartIso,
              bounds?.endIso ?? st.windowEndIso,
            ),
            windowStartIso: bounds?.startIso ?? st.windowStartIso,
            windowEndIso: bounds?.endIso ?? st.windowEndIso,
          };
        });
        break;
      }
      case "liveness.update":
      case "liveness.tick":
        set((st) => ({ liveness: mergeLivenessInfo(st.liveness, env.data) }));
        break;
      case "leaderboard.update":
        set({ leaderboard: env.data.top });
        break;
      case "calibration.start":
      case "calibration.end":
        set((st) => ({
          calibration: {
            ...env.data,
            last_timing: mergeTimingInfo(
              st.calibration.last_timing,
              env.data.last_timing,
            ),
          },
        }));
        break;
      case "trade.append":
        handleTrade(env.data, get, set);
        break;
      default:
        break;
    }
  },

  tickWindow: (nowMs = Date.now()) =>
    set((st) => ({
      window: computeWindowStateFromBounds(
        st.window,
        st.windowStartIso,
        st.windowEndIso,
        nowMs,
      ),
    })),

  consumeFlash: (id) =>
    set((st) => ({ flashQueue: st.flashQueue.filter((f) => f.id !== id) })),
}));

// PriceChart filters by window bounds at render time and backend collectors
// reset their own deques on slug boundaries, so we don't clear stored series
// here. Kept as a hook point for future per-slug logic.
function ensureSlug(
  _st: DashState,
  _newSlug: string | null,
): Partial<DashState> {
  return {};
}

function handleTrade(
  ev: TradeEvent,
  get: () => DashState,
  set: (partial: Partial<DashState>) => void,
) {
  if (ev.instance_id !== get().selectedInstanceId) return;
  const st = get();
  const ctx = {
    position: st.position,
    terminal: st.terminal,
    window: st.window,
    windowStartIso: st.windowStartIso,
    windowEndIso: st.windowEndIso,
    modelUp: st.modelUp,
    modelDown: st.modelDown,
    equity: st.equity,
    equitySeries: st.equitySeries,
    markers: st.markers,
    flashQueue: st.flashQueue,
    startingCapital:
      st.instance?.starting_capital ?? st.sharedConfig.starting_capital ?? 1000,
    tpPct: st.instance?.params?.tp_pct ?? null,
    slPct: st.instance?.params?.sl_pct ?? null,
  };

  const marketContext = nextMarketContext(ctx, ev);
  const chartContext = nextEntryChartContext(ctx, ev);
  const liveEquity = nextLiveEquity(ctx, ev);
  const activeSlug =
    marketContext.terminal?.market?.slug ?? st.terminal?.market?.slug ?? null;

  set({
    trades: [ev, ...st.trades].slice(0, 200),
    flashQueue: nextFlashQueue(st.flashQueue, ev),
    markers: nextMarkers(st.markers, ev, activeSlug),
    position: nextPositionState(ctx, ev),
    ...marketContext,
    ...(chartContext ?? {}),
    ...(liveEquity ?? {}),
  });
}
