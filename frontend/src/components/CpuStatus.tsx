import { useDash } from "../lib/store";

export default function CpuStatus() {
  const cpuPct = useDash((s) => s.liveness?.cpu_pct ?? null);

  if (cpuPct == null) {
    return (
      <span className="chip chip-mute font-mono">
        <span className="text-slate-500">cpu</span>
        <span className="text-slate-300">--</span>
      </span>
    );
  }

  const rounded = Math.round(cpuPct);
  const chipClass =
    rounded < 45 ? "chip-up" : rounded < 75 ? "chip-warn" : "chip-down";

  return (
    <span className={`chip ${chipClass} font-mono`}>
      <span>cpu</span>
      <span>{rounded}%</span>
    </span>
  );
}
