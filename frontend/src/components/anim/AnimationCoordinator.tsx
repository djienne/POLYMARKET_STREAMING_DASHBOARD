import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { useDash } from "../../lib/store";
import { fmtMoney } from "../../lib/format";

// dicaprio.gif is 84 frames × 50 ms = exactly 4200 ms per loop (header loop=0).
// We remount the <img> once at the natural loop boundary so the browser replays it
// without leaving the overlay visibly frozen on the last frame.
const GIF_LOOP_MS = 4200;
const GIF_LOOPS = 2;

// Floating toast-style burst for each new fill event
export default function AnimationCoordinator() {
  const flashes = useDash((s) => s.flashQueue);
  const consumeFlash = useDash((s) => s.consumeFlash);
  const winFlash = flashes.find((f) => f.kind === "win");

  useEffect(() => {
    if (flashes.length === 0) return;
    // Wins dismiss exactly after the gif has played GIF_LOOPS full runs (no partial loop).
    const WIN_MS = GIF_LOOPS * GIF_LOOP_MS + 300;  // +300ms tail so last loop isn't cut
    const timers = flashes.map((f) =>
      window.setTimeout(() => consumeFlash(f.id), f.kind === "win" ? WIN_MS : 3500),
    );
    return () => {
      timers.forEach((t) => clearTimeout(t));
    };
  }, [flashes, consumeFlash]);

  return (
    <>
      {/* Dicaprio celebration — pops up on every winning trade */}
      <AnimatePresence>
        {winFlash && (
          <motion.div
            key={winFlash.id}
            initial={{ opacity: 0, scale: 0.6, rotate: -4 }}
            animate={{ opacity: 1, scale: 1, rotate: 0 }}
            exit={{ opacity: 0, scale: 0.85, rotate: 3 }}
            transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
            className="fixed inset-0 z-[60] flex items-center justify-center pointer-events-none"
          >
            <div className="relative flex flex-col items-center">
              {/* Glow backdrop */}
              <div className="absolute inset-0 -m-10 rounded-full bg-emerald-500/20 blur-3xl" />
              {/* The GIF itself — remounted at loop boundaries so it plays GIF_LOOPS
                   times even when the file's own loop-count is 1. The last loop is NOT
                   cut: we stop remounting after (GIF_LOOPS - 1) ticks and let the final
                   playthrough run to completion before the overlay dismisses. */}
              <LoopingGif
                src="/dicaprio.gif"
                className="relative w-[26vw] max-w-[420px] min-w-[260px] rounded-2xl border-2 border-emerald-400/60 shadow-[0_0_60px_rgba(52,211,153,0.55)]"
              />
              {/* PnL chip */}
              <div className="relative -mt-4 px-4 py-1.5 rounded-full bg-ink-950/90 border border-emerald-400/60 font-mono text-emerald-200 text-lg shadow-2xl">
                WIN {fmtMoney(winFlash.amount ?? 0)}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="fixed top-16 right-4 z-40 flex flex-col gap-2 pointer-events-none">
      <AnimatePresence>
        {flashes.map((f) => {
          const palette =
            f.kind === "win"
              ? {
                  bg: "bg-emerald-950/92",
                  border: "border-emerald-300/70",
                  text: "text-emerald-50",
                  accent: "text-emerald-200",
                  glow: "shadow-[0_0_32px_rgba(52,211,153,0.30)]",
                }
              : f.kind === "loss"
                ? {
                    bg: "bg-rose-950/92",
                    border: "border-rose-300/70",
                    text: "text-rose-50",
                    accent: "text-rose-200",
                    glow: "shadow-[0_0_32px_rgba(251,113,133,0.28)]",
                  }
                : {
                    bg:
                      f.direction === "DOWN"
                        ? "bg-rose-950/92"
                        : "bg-emerald-950/92",
                    border:
                      f.direction === "DOWN"
                        ? "border-rose-300/70"
                        : "border-emerald-300/70",
                    text:
                      f.direction === "DOWN"
                        ? "text-rose-50"
                        : "text-emerald-50",
                    accent:
                      f.direction === "DOWN"
                        ? "text-rose-200"
                        : "text-emerald-200",
                    glow:
                      f.direction === "DOWN"
                        ? "shadow-[0_0_28px_rgba(251,113,133,0.22)]"
                        : "shadow-[0_0_28px_rgba(52,211,153,0.22)]",
                  };
          const title =
            f.kind === "entry"
              ? `Opened ${f.direction ?? ""}`
              : f.kind === "win"
                ? "Win"
                : "Loss";
          return (
            <motion.div
              key={f.id}
              initial={{ opacity: 0, x: 40, scale: 0.96 }}
              animate={{ opacity: 1, x: 0, scale: 1 }}
              exit={{ opacity: 0, x: 40, scale: 0.96 }}
              transition={{ duration: 0.4, ease: "easeOut" }}
              className={`card ${palette.bg} ${palette.border} ${palette.text} ${palette.glow} px-5 py-4 min-w-[260px] backdrop-blur-md ring-1 ring-black/30 shadow-2xl`}
            >
              <div className={`text-[11px] uppercase tracking-[0.22em] ${palette.accent} opacity-85`}>
                {f.kind === "entry" ? "position" : "realized"}
              </div>
              <div className="flex items-baseline justify-between mt-0.5">
                <span className="text-base font-semibold">{title}</span>
                {f.amount != null && (
                  <span className={`font-mono text-xl font-semibold ${palette.accent}`}>
                    {fmtMoney(f.amount)}
                  </span>
                )}
              </div>
            </motion.div>
          );
        })}
      </AnimatePresence>
      </div>
    </>
  );
}

function LoopingGif({ src, className }: { src: string; className?: string }) {
  const [loop, setLoop] = useState(0);
  useEffect(() => {
    if (loop >= GIF_LOOPS - 1) return;  // last loop runs uninterrupted to its end
    const id = window.setTimeout(() => setLoop((n) => n + 1), GIF_LOOP_MS);
    return () => clearTimeout(id);
  }, [loop]);
  // Query string guarantees a fresh decode even if the browser cached aggressively.
  return (
    <img
      key={loop}
      src={loop === 0 ? src : `${src}?r=${loop}`}
      alt="cheers"
      className={className}
    />
  );
}
