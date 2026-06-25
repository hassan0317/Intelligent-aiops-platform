import clsx from "clsx";

export const cn = (...a) => clsx(...a);

export const fmt = (v, d = 0) =>
  v == null || Number.isNaN(Number(v)) ? "–" : Number(v).toFixed(d);
export const fmtInt = (v) =>
  v == null || Number.isNaN(Number(v)) ? "–" : Math.round(Number(v)).toLocaleString();

// The platform displays all wall-clock times in Pakistan Standard Time (UTC+5),
// independent of the viewer's browser. Timestamps are STORED in UTC; we only convert
// for display via Intl (the full tz database is built into the browser). Accepts an
// ISO string or epoch-seconds.
export const TZ = "Asia/Karachi";
const _fmtHMS = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
const _fmtHM = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour12: false, hour: "2-digit", minute: "2-digit" });
const _toDate = (v) => (v == null || v === "" ? null : (typeof v === "number" ? new Date(v * 1000) : new Date(v)));
export const tzTime = (v) => { const d = _toDate(v); return d && !Number.isNaN(d.getTime()) ? _fmtHMS.format(d) : "–"; };
export const tzHM = (v) => { const d = _toDate(v); return d && !Number.isNaN(d.getTime()) ? _fmtHM.format(d) : "–"; };

export const SERVICES = ["frontend-api", "orders-service", "payments-service"];
export const FAULTS = ["latency", "cpu", "memory", "error"];

// near-black palette + semantic status (Datadog × Linear)
export const COLORS = {
  accent: "#6366f1",   // indigo
  emerald: "#10b981",
  amber: "#f59e0b",
  red: "#ef4444",
  violet: "#8b5cf6",
  cyan: "#06b6d4",
  grid: "#27272a",
  axis: "#52525b",
};

// status -> tailwind tone + hex
export const STATUS = {
  ok: { label: "Healthy", tone: "emerald", hex: COLORS.emerald },
  warmup: { label: "Warming up", tone: "zinc", hex: "#a1a1aa" },
  confirming: { label: "Confirming", tone: "amber", hex: COLORS.amber },
  suspected: { label: "Suspected", tone: "amber", hex: COLORS.amber },
  incident: { label: "Incident", tone: "red", hex: COLORS.red },
  starting: { label: "Starting", tone: "zinc", hex: "#a1a1aa" },
};

export const toneClasses = {
  emerald: "bg-emerald-500/10 text-emerald-400 ring-emerald-500/30",
  amber: "bg-amber-500/10 text-amber-400 ring-amber-500/30",
  red: "bg-red-500/10 text-red-400 ring-red-500/30",
  zinc: "bg-zinc-500/10 text-zinc-300 ring-zinc-500/30",
  indigo: "bg-indigo-500/10 text-indigo-300 ring-indigo-500/30",
};
