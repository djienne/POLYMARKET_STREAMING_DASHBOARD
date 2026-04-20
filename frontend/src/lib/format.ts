export function fmtMoney(v: number | null | undefined, d = 2): string {
  if (v == null || Number.isNaN(v)) return "—";
  const sign = v < 0 ? "−" : v > 0 ? "+" : "";
  return `${sign}$${Math.abs(v).toFixed(d)}`;
}

export function fmtPct(v: number | null | undefined, d = 2): string {
  if (v == null || Number.isNaN(v)) return "—";
  const sign = v < 0 ? "−" : v > 0 ? "+" : "";
  return `${sign}${Math.abs(v).toFixed(d)}%`;
}

export function fmtProb(v: number | null | undefined, d = 4): string {
  if (v == null || Number.isNaN(v)) return "—";
  return v.toFixed(d);
}

export function fmtRatio(v: number | null | undefined, d = 3): string {
  if (v == null || Number.isNaN(v)) return "—";
  return v.toFixed(d);
}

export function fmtDuration(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return "—";
  const s = Math.max(0, Math.floor(seconds));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${r.toString().padStart(2, "0")}`;
}

export function pnlColor(v: number | null | undefined): string {
  if (v == null) return "text-slate-400";
  if (v > 0) return "text-emerald-300";
  if (v < 0) return "text-rose-300";
  return "text-slate-300";
}
