import { useDash } from "../lib/store";
import ModeBadge from "./ModeBadge";
import CalibrationStatus from "./CalibrationStatus";
import CpuStatus from "./CpuStatus";

export default function TopStrip() {
  const mode = useDash((s) => s.mode);

  return (
    <header className="sticky top-0 z-20 bg-ink-950/85 backdrop-blur border-b border-ink-800">
      <div className="max-w-[1680px] mx-auto flex items-center gap-4 px-4 lg:px-6 py-3">
        <div className="flex items-center gap-3">
          <img src="/polymarket.svg" alt="Polymarket" className="h-11 w-auto" />
          <img src="/bitcoin.svg" alt="BTC" className="w-9 h-9" />
          <div className="leading-tight">
            <span className="text-sm font-semibold text-slate-100">
              BTC 15-min UP / DOWN
            </span>
            <div className="text-[10px] text-slate-500 uppercase tracking-widest mt-0.5">
              Streaming Dashboard
            </div>
          </div>
        </div>

        <ModeBadge mode={mode} />

        {mode === "live" && (
          <a
            href="https://polymarket.com/@freqtradefr"
            target="_blank"
            rel="noopener noreferrer"
            title="View real-money account on Polymarket"
            className="font-mono text-[11px] tracking-widest text-amber-300/90 hover:text-amber-200 border border-amber-500/30 bg-amber-500/5 hover:bg-amber-500/10 rounded px-2 py-0.5 transition-colors"
          >
            @freqtradefr ↗
          </a>
        )}

        <div className="flex-1" />
        <div className="flex items-center gap-2">
          <CalibrationStatus />
          <CpuStatus />
        </div>
      </div>
    </header>
  );
}
