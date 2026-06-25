import {
  AreaChart, Area, LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import { COLORS, tzHM } from "../lib/utils";

// Prometheus query_range result -> recharts rows merged on timestamp
export function frameMatrix(result, labelOf) {
  const byTs = {};
  const keys = [];
  (result || []).forEach((s) => {
    const key = labelOf(s.metric || {});
    if (!keys.includes(key)) keys.push(key);
    (s.values || []).forEach(([ts, v]) => {
      const t = Number(ts);
      byTs[t] = byTs[t] || { t };
      const num = Number(v);
      byTs[t][key] = Number.isFinite(num) ? num : 0;
    });
  });
  const rows = Object.values(byTs).sort((a, b) => a.t - b.t).map((r) => ({
    ...r,
    label: tzHM(r.t),
  }));
  return { rows, keys };
}

function DarkTooltip({ active, payload, label, unit }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-edge bg-[#16161a] px-2.5 py-1.5 text-[11px] shadow-xl">
      <div className="text-zinc-500 mb-1">{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-sm" style={{ background: p.color }} />
          <span className="text-zinc-300">{p.dataKey}</span>
          <span className="nums ml-auto text-zinc-100">{Number(p.value).toFixed(unit === "ms" ? 0 : 2)}{unit ? ` ${unit}` : ""}</span>
        </div>
      ))}
    </div>
  );
}

const PALETTE = [COLORS.accent, COLORS.cyan, COLORS.violet, COLORS.amber, COLORS.emerald];

export function TimeChart({ rows, keys, height = 200, unit, area = true, colors }) {
  const cols = colors || PALETTE;
  const C = area ? AreaChart : LineChart;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <C data={rows} margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
        <defs>
          {keys.map((k, i) => (
            <linearGradient key={k} id={`g-${i}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={cols[i % cols.length]} stopOpacity={0.28} />
              <stop offset="100%" stopColor={cols[i % cols.length]} stopOpacity={0} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid stroke={COLORS.grid} vertical={false} />
        <XAxis dataKey="label" stroke={COLORS.axis} tick={{ fontSize: 10, fill: COLORS.axis }} tickLine={false} axisLine={false} minTickGap={28} />
        <YAxis stroke={COLORS.axis} tick={{ fontSize: 10, fill: COLORS.axis }} tickLine={false} axisLine={false} width={42} />
        <Tooltip content={<DarkTooltip unit={unit} />} />
        {keys.map((k, i) =>
          area ? (
            <Area key={k} type="monotone" dataKey={k} stroke={cols[i % cols.length]} strokeWidth={1.75}
              fill={`url(#g-${i})`} isAnimationActive={false} />
          ) : (
            <Line key={k} type="monotone" dataKey={k} stroke={cols[i % cols.length]} strokeWidth={1.75}
              dot={false} isAnimationActive={false} />
          )
        )}
      </C>
    </ResponsiveContainer>
  );
}

export function HBars({ data, height = 200, hex = COLORS.accent }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 16, left: 8, bottom: 0 }}>
        <CartesianGrid stroke={COLORS.grid} horizontal={false} />
        <XAxis type="number" stroke={COLORS.axis} tick={{ fontSize: 10, fill: COLORS.axis }} tickLine={false} axisLine={false} />
        <YAxis type="category" dataKey="name" width={150} stroke={COLORS.axis}
          tick={{ fontSize: 11, fill: "#a1a1aa" }} tickLine={false} axisLine={false} />
        <Tooltip content={<DarkTooltip />} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
        <Bar dataKey="value" radius={[0, 3, 3, 0]} isAnimationActive={false}>
          {data.map((d, i) => <Cell key={i} fill={d.hex || hex} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
