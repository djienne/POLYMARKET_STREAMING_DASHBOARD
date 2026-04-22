import { useEffect, useRef } from "react";
import { api } from "./lib/api";
import { useDash } from "./lib/store";
import { createWs, WsManager } from "./lib/ws";

import TopStrip from "./components/TopStrip";
import ProbabilityPanel from "./components/ProbabilityPanel";
import EdgeRatioPanel from "./components/EdgeRatioPanel";
import MarketInfoCard from "./components/MarketInfoCard";
import WindowTimer from "./components/WindowTimer";
import PositionCard from "./components/PositionCard";
import InstanceStatsCard from "./components/InstanceStatsCard";
import EquitySparkline from "./components/EquitySparkline";
import PriceChart from "./components/PriceChart";
import TradeFeed from "./components/TradeFeed";
import Footer from "./components/Footer";
import AnimationCoordinator from "./components/anim/AnimationCoordinator";

export default function App() {
  const wsRef = useRef<WsManager | null>(null);
  const setAllInstances = useDash((s) => s.setAllInstances);
  const setSelected = useDash((s) => s.setSelected);
  const applyBootstrap = useDash((s) => s.applyBootstrap);
  const applyEnvelope = useDash((s) => s.applyEnvelope);
  const setWsStatus = useDash((s) => s.setWsStatus);
  const selected = useDash((s) => s.selectedInstanceId);
  const windowStartIso = useDash((s) => s.windowStartIso);

  useEffect(() => {
    // Allow overriding the selected instance via ?instance_id=N for dev / debugging
    // without surfacing the multi-instance reality in the UI.
    const urlId = new URLSearchParams(window.location.search).get("instance_id");
    const initialId = urlId != null && !Number.isNaN(Number(urlId)) ? Number(urlId) : selected;
    if (initialId !== selected) setSelected(initialId);
    api.bootstrap(initialId).then(applyBootstrap).catch(console.error);
    api.instances().then(setAllInstances).catch(console.error);

    const ws = createWs();
    wsRef.current = ws;
    ws.subscribeStatus(setWsStatus);
    ws.subscribe((env) => applyEnvelope(env));
    ws.connect();
    return () => ws.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    wsRef.current?.selectInstance(selected);
  }, [selected]);

  // Re-fetch bootstrap whenever the 15-min market window changes. The WS stream
  // publishes model.update only when a new log line is parsed, which can leave
  // the chart stuck at the 0.5 seed for up to a minute after window rollover
  // (or indefinitely if WS events are dropped). Bootstrap re-scopes all series
  // to the new window and unsticks the chart within one poll cycle.
  useEffect(() => {
    if (!windowStartIso) return;
    api.bootstrap(selected).then(applyBootstrap).catch(console.error);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [windowStartIso]);

  return (
    <div className="min-h-screen w-full bg-ink-950 flex justify-center">
      {/* Lock to 16:9 for 1080p streaming; body scrolls on viewports shorter than the frame */}
      <div className="stream-frame flex flex-col">
        <TopStrip />

        <main className="flex-1 min-h-0 px-4 py-3 grid grid-cols-[minmax(0,1fr)_320px] gap-3">
          <div className="min-h-0 grid grid-rows-[minmax(0,22fr)_minmax(0,22fr)_minmax(0,15fr)_minmax(0,27fr)] gap-3">
            {/* Row 1: probabilities + edge */}
            <section className="grid grid-cols-[minmax(0,2.35fr)_minmax(320px,0.9fr)] gap-3 min-h-0">
              <div className="min-h-0">
                <ProbabilityPanel />
              </div>
              <div className="min-h-0 self-start">
                <EdgeRatioPanel />
              </div>
            </section>

            {/* Row 2: live UP/DOWN price chart (full width) */}
            <section className="min-h-0">
              <PriceChart />
            </section>

            {/* Row 3: market / window / position */}
            <section className="grid grid-cols-3 gap-3 min-h-0">
              <MarketInfoCard />
              <WindowTimer />
              <PositionCard />
            </section>

            {/* Row 4: instance stats + equity */}
            <section className="grid grid-cols-3 gap-3 min-h-0">
              <div className="col-span-2 min-h-0">
                <InstanceStatsCard />
              </div>
              <div className="min-h-0">
                <EquitySparkline />
              </div>
            </section>
          </div>

          {/* Right rail: tall trade feed */}
          <div className="min-h-0">
            <TradeFeed />
          </div>
        </main>

        <Footer />
        <AnimationCoordinator />
      </div>
    </div>
  );
}
