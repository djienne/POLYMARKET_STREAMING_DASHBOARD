import { useDash } from "../lib/store";

// Small chip next to CpuStatus showing where the live trader is running and
// the Polymarket latency measured from that side. Never surfaces host/IP —
// only a friendly label from the backend (e.g. "VPS Tokyo", "local").
export default function LocationChip() {
  const liveness = useDash((s) => s.liveness);
  const loc = liveness?.execution_location ?? null;
  const label = liveness?.execution_label ?? null;
  const pingMs = liveness?.polymarket_ping_ms ?? null;

  if (!loc && pingMs == null) {
    return (
      <span className="chip chip-mute font-mono w-[176px] min-w-[176px] items-center gap-1.5 pl-2 pr-1">
        <span className="text-slate-500">loc</span>
        <span className="text-slate-300">--</span>
      </span>
    );
  }

  // Location dot color:
  //   local → slate neutral
  //   vps   → amber (it's the live real-money fast path)
  //   stopped / unknown → muted
  const dotClass =
    loc === "vps"
      ? "bg-amber-300"
      : loc === "local"
        ? "bg-slate-300"
        : "bg-slate-600";

  // Ping color thresholds: <100ms great (emerald), <200ms ok (slate), ≥200ms warn (amber)
  const pingClass =
    pingMs == null
      ? "text-slate-400"
      : pingMs < 100
        ? "text-emerald-300"
        : pingMs < 200
          ? "text-slate-100"
          : "text-amber-300";

  const displayLabel =
    label ?? (loc === "vps" ? "VPS" : loc === "local" ? "local" : (loc ?? "—"));

  return (
    <span
      className="chip chip-mute font-mono w-[182px] min-w-[182px] items-center gap-3 pl-2 pr-1"
      title={
        pingMs != null
          ? `Polymarket CLOB latency measured from ${displayLabel}: ${pingMs.toFixed(0)} ms`
          : `Live trader running on ${displayLabel}`
      }
    >
      <span className="inline-flex items-center gap-1.5 min-w-0">
        <span className={`inline-block w-1.5 h-1.5 rounded-full shrink-0 ${dotClass}`} />
        <span className="text-slate-300 whitespace-nowrap">{displayLabel}</span>
      </span>
      {pingMs != null && (
        <span className={`${pingClass} inline-flex w-[44px] justify-end shrink-0`}>
          {pingMs.toFixed(0)}ms
        </span>
      )}
    </span>
  );
}
