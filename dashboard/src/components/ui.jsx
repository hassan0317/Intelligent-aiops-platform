import { cn } from "../lib/utils";
import {
  LineChart, Line, ResponsiveContainer,
} from "recharts";

export function Card({ className, children }) {
  return (
    <div className={cn("rounded-xl border border-edge bg-panel shadow-soft", className)}>{children}</div>
  );
}

export function Panel({ title, subtitle, right, icon: Icon, className, bodyClass, children }) {
  return (
    <Card className={cn("flex flex-col", className)}>
      {(title || right) && (
        <div className="flex items-center justify-between px-4 pt-3.5 pb-3 border-b border-edge/70">
          <div className="flex items-center gap-2 min-w-0">
            {Icon && <Icon className="h-4 w-4 text-zinc-500 shrink-0" />}
            <div className="min-w-0">
              <div className="text-[13px] font-medium text-zinc-200 truncate">{title}</div>
              {subtitle && <div className="text-[11px] text-zinc-500 truncate">{subtitle}</div>}
            </div>
          </div>
          {right}
        </div>
      )}
      <div className={cn("p-4", bodyClass)}>{children}</div>
    </Card>
  );
}

const TONE = {
  emerald: "bg-emerald-500/10 text-emerald-400 ring-1 ring-inset ring-emerald-500/25",
  amber: "bg-amber-500/10 text-amber-400 ring-1 ring-inset ring-amber-500/25",
  red: "bg-red-500/10 text-red-400 ring-1 ring-inset ring-red-500/25",
  zinc: "bg-zinc-500/10 text-zinc-300 ring-1 ring-inset ring-zinc-500/25",
  indigo: "bg-indigo-500/10 text-indigo-300 ring-1 ring-inset ring-indigo-500/25",
  violet: "bg-violet-500/10 text-violet-300 ring-1 ring-inset ring-violet-500/25",
};

export function Badge({ tone = "zinc", className, children }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[11px] font-medium",
      TONE[tone], className)}>{children}</span>
  );
}

export function Dot({ tone = "emerald", pulse }) {
  const c = { emerald: "bg-emerald-400", amber: "bg-amber-400", red: "bg-red-400", zinc: "bg-zinc-400", indigo: "bg-indigo-400" }[tone];
  return <span className={cn("inline-block h-2 w-2 rounded-full", c, pulse && "animate-pulsedot")} />;
}

export function Stat({ label, value, unit, tone = "zinc", icon: Icon, hint }) {
  const valTone = { emerald: "text-emerald-400", amber: "text-amber-400", red: "text-red-400", zinc: "text-zinc-100", indigo: "text-indigo-300" }[tone];
  return (
    <Card className="px-4 py-3.5 lift hover:border-zinc-700/80">
      <div className="flex items-center justify-between">
        <span className="text-[11px] uppercase tracking-wide text-zinc-500">{label}</span>
        {Icon && <Icon className="h-3.5 w-3.5 text-zinc-600" />}
      </div>
      <div className="mt-1.5 flex items-baseline gap-1">
        <span className={cn("nums text-2xl font-semibold leading-none", valTone)}>{value}</span>
        {unit && <span className="text-xs text-zinc-500">{unit}</span>}
      </div>
      {hint && <div className="mt-1 text-[11px] text-zinc-600 truncate">{hint}</div>}
    </Card>
  );
}

export function Button({ variant = "ghost", className, children, ...props }) {
  const v = {
    primary: "bg-indigo-600 hover:bg-indigo-500 text-white border-indigo-500/40",
    ghost: "bg-transparent hover:bg-zinc-800/70 text-zinc-200 border-edge",
    danger: "bg-red-600/90 hover:bg-red-500 text-white border-red-500/40",
    subtle: "bg-zinc-800/60 hover:bg-zinc-700/70 text-zinc-200 border-edge",
  }[variant];
  return (
    <button
      className={cn("inline-flex items-center justify-center gap-1.5 rounded-lg border px-3 py-1.5 text-[13px] font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed", v, className)}
      {...props}
    >{children}</button>
  );
}

export function Ring({ value = 0, max = 1, size = 132, stroke = 11, hex = "#6366f1", label, sub }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(1, value / max));
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#27272a" strokeWidth={stroke} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={hex} strokeWidth={stroke}
          strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - pct)}
          style={{ transition: "stroke-dashoffset .6s ease, stroke .4s ease" }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="nums text-2xl font-semibold" style={{ color: hex }}>{label}</span>
        {sub && <span className="text-[11px] text-zinc-500 mt-0.5">{sub}</span>}
      </div>
    </div>
  );
}

export function Spark({ data = [], dataKey = "p", hex = "#6366f1", height = 34 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 4, bottom: 0, left: 0, right: 0 }}>
        <Line type="monotone" dataKey={dataKey} stroke={hex} strokeWidth={1.75} dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function Skeleton({ className }) {
  return <div className={cn("animate-pulse rounded-md bg-zinc-800/60", className)} />;
}

export function Empty({ icon: Icon, title, hint }) {
  return (
    <div className="flex flex-col items-center justify-center py-8 text-center">
      {Icon && <Icon className="h-6 w-6 text-zinc-600" />}
      <div className="mt-2 text-[13px] text-zinc-400">{title}</div>
      {hint && <div className="text-[11px] text-zinc-600 mt-0.5">{hint}</div>}
    </div>
  );
}

export function Toggle({ checked, onChange }) {
  return (
    <button onClick={() => onChange(!checked)}
      className={cn("relative h-5 w-9 rounded-full transition-colors", checked ? "bg-indigo-600" : "bg-zinc-700")}
      role="switch" aria-checked={checked}>
      <span className={cn("absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform", checked ? "translate-x-4" : "translate-x-0.5")} />
    </button>
  );
}
