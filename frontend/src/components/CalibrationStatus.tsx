import { AnimatePresence, motion } from "framer-motion";
import { useDash } from "../lib/store";

export default function CalibrationStatus() {
  const cal = useDash((s) => s.calibration);
  const timing = cal.last_timing;

  return (
    <AnimatePresence mode="wait">
      {cal.active ? (
        <motion.div
          key="active"
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          className="chip chip-warn"
        >
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-400"></span>
          </span>
          <span>
            Calculating new calibration
            {cal.elapsed_s != null ? ` · ${cal.elapsed_s.toFixed(0)}s` : "…"}
          </span>
        </motion.div>
      ) : timing && (timing.surface_fit_s || timing.mc_s) ? (
        <motion.div
          key="done"
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          className="chip chip-mute font-mono"
        >
          <span className="text-slate-500">calibrated</span>
          {timing.surface_fit_s != null && (
            <span className="text-slate-300">
              fit {timing.surface_fit_s.toFixed(2)}s
            </span>
          )}
          {timing.mc_s != null && (
            <span className="text-slate-300">
              mc {timing.mc_s.toFixed(2)}s
            </span>
          )}
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
