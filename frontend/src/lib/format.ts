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

// ──────── Local time (Europe/Paris — CET/CEST; same as Amsterdam). ────────
// Intl handles DST automatically.
const TZ = "Europe/Paris";

function _toDate(ts: number | string | Date | null | undefined): Date | null {
  if (ts == null) return null;
  const d = ts instanceof Date ? ts : new Date(ts);
  return Number.isFinite(d.getTime()) ? d : null;
}

export function fmtLocalHM(ts: number | string | Date | null | undefined): string {
  const d = _toDate(ts);
  if (!d) return "—";
  return d.toLocaleTimeString("en-GB", {
    hour12: false,
    timeZone: TZ,
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function fmtLocalHMS(ts: number | string | Date | null | undefined): string {
  const d = _toDate(ts);
  if (!d) return "—";
  return d.toLocaleTimeString("en-GB", {
    hour12: false,
    timeZone: TZ,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function fmtLocalDate(ts: number | string | Date | null | undefined): string {
  const d = _toDate(ts);
  if (!d) return "—";
  return d.toLocaleDateString("en-GB", {
    timeZone: TZ,
    month: "2-digit",
    day: "2-digit",
  });
}

export function fmtLocalFull(ts: number | string | Date | null | undefined): string {
  const d = _toDate(ts);
  if (!d) return "—";
  return d.toLocaleString("en-GB", {
    timeZone: TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}
