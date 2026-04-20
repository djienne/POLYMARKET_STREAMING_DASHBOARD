import { AnimatePresence, motion } from "framer-motion";
import { useEffect } from "react";
import { useDash } from "../../lib/store";
import { fmtMoney } from "../../lib/format";

// Floating toast-style burst for each new fill event
export default function AnimationCoordinator() {
  const flashes = useDash((s) => s.flashQueue);
  const consumeFlash = useDash((s) => s.consumeFlash);

  useEffect(() => {
    if (flashes.length === 0) return;
    const timers = flashes.map((f) =>
      window.setTimeout(() => consumeFlash(f.id), 3500),
    );
    return () => {
      timers.forEach((t) => clearTimeout(t));
    };
  }, [flashes, consumeFlash]);

  return (
    <div className="fixed top-16 right-4 z-40 flex flex-col gap-2 pointer-events-none">
      <AnimatePresence>
        {flashes.map((f) => {
          const palette =
            f.kind === "win"
              ? {
                  bg: "bg-emerald-500/20",
                  border: "border-emerald-400/40",
                  text: "text-emerald-200",
                }
              : f.kind === "loss"
                ? {
                    bg: "bg-rose-500/20",
                    border: "border-rose-400/40",
                    text: "text-rose-200",
                  }
                : {
                    bg:
                      f.direction === "DOWN"
                        ? "bg-rose-500/20"
                        : "bg-emerald-500/20",
                    border:
                      f.direction === "DOWN"
                        ? "border-rose-400/40"
                        : "border-emerald-400/40",
                    text:
                      f.direction === "DOWN"
                        ? "text-rose-200"
                        : "text-emerald-200",
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
              className={`card ${palette.bg} ${palette.border} ${palette.text} px-4 py-3 min-w-[200px] shadow-2xl`}
            >
              <div className="text-[10px] uppercase tracking-widest opacity-70">
                {f.kind === "entry" ? "position" : "realized"}
              </div>
              <div className="flex items-baseline justify-between mt-0.5">
                <span className="font-semibold">{title}</span>
                {f.amount != null && (
                  <span className="font-mono">{fmtMoney(f.amount)}</span>
                )}
              </div>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
