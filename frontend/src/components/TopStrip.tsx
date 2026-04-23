import { useDash } from "../lib/store";
import ModeBadge from "./ModeBadge";
import CalibrationStatus from "./CalibrationStatus";
import CpuStatus from "./CpuStatus";
import InstanceSelector from "./InstanceSelector";
import BotStatusBanner from "./BotStatusBanner";
import LocationChip from "./LocationChip";

export default function TopStrip() {
  const mode = useDash((s) => s.mode);

  return (
    <header className="sticky top-0 z-20 border-b border-ink-800/90 bg-ink-950/72 backdrop-blur-xl shadow-[0_12px_36px_rgba(2,6,23,0.34)]">
      <div className="max-w-[1680px] mx-auto flex items-center gap-4 px-4 lg:px-6 py-3">
        <div className="flex items-center gap-3 rounded-xl border border-ink-800/80 bg-ink-900/55 px-3 py-1.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.02)]">
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

        {mode === "dry_run" && <InstanceSelector />}

        {mode === "live" && (
          <div className="rounded-xl border border-amber-500/25 bg-[linear-gradient(180deg,rgba(245,158,11,0.12),rgba(245,158,11,0.05))] px-3 py-1.5 leading-tight shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
            <div className="text-[9px] uppercase tracking-[0.18em] text-amber-200/60">
              Live Account
            </div>
            <div className="font-mono text-[11px] text-amber-300/90">
              https://polymarket.com/@freqtradefr
            </div>
          </div>
        )}

        <div className="flex-1 min-w-0">
          <BotStatusBanner compact />
        </div>
        <div className="flex shrink-0 items-center justify-end gap-2.5">
          <CalibrationStatus />
          <CpuStatus />
          <LocationChip />
        </div>
      </div>
    </header>
  );
}
