import { useDash } from "../lib/store";

export default function Footer() {
  const ws = useDash((s) => s.wsStatus);
  const live = useDash((s) => s.liveness);
  const cal = useDash((s) => s.calibration);
  const t = cal.last_timing;

  return (
    <footer className="border-t border-ink-800 bg-ink-950/90 backdrop-blur">
      <div className="max-w-[1680px] mx-auto px-4 lg:px-6 py-2 flex flex-wrap gap-4 items-center text-[11px] font-mono">
        <Dot label="backend" ok={true} />
        <Dot label="ws" ok={ws === "open"} info={ws} />
        <Dot label="bot" ok={!!live?.bot_live} />
        <span className="text-slate-500">
          last tick{" "}
          <span className="text-slate-300">
            {live?.terminal_age_s != null
              ? `${live.terminal_age_s.toFixed(1)}s`
              : "—"}
          </span>
        </span>
        <span className="text-slate-500 ml-auto">
          {t?.surface_fit_s != null && (
            <>
              fit{" "}
              <span className="text-slate-300">
                {t.surface_fit_s.toFixed(2)}s
              </span>
              {"  "}
            </>
          )}
          {t?.mc_s != null && (
            <>
              mc <span className="text-slate-300">{t.mc_s.toFixed(2)}s</span>
            </>
          )}
        </span>
        <DevWinTrigger />
      </div>
    </footer>
  );
}

/**
 * Hidden dev button — a 6×6 dot tucked at the very end of the footer.
 * Click to fire a synthetic "win" flash so the dicaprio.gif overlay can be
 * verified without waiting for a real TP. Not visually obvious: 10% opacity
 * at rest, 70% on hover.
 */
function DevWinTrigger() {
  return (
    <button
      type="button"
      title="trigger win"
      aria-label="trigger win"
      onClick={() => {
        useDash.setState((st) => ({
          flashQueue: [
            ...st.flashQueue,
            {
              id: `dev-${Date.now()}`,
              kind: "win",
              direction: "UP",
              amount: 4.2,
              at: Date.now(),
            },
          ],
        }));
      }}
      className="w-1.5 h-1.5 rounded-full bg-slate-500 opacity-10 hover:opacity-70 transition-opacity"
    />
  );
}

function Dot({
  label,
  ok,
  info,
}: {
  label: string;
  ok: boolean;
  info?: string;
}) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className={`dot ${
          ok
            ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.9)]"
            : "bg-rose-400"
        }`}
      />
      <span className="text-slate-400">{label}</span>
      {info && <span className="text-slate-500">{info}</span>}
    </span>
  );
}
