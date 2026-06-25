import { useState } from "react";
import { useServices, useMetricsRange, useLogs } from "../lib/hooks";
import { useOverview } from "../lib/hooks";
import { SERVICES, fmt, COLORS, tzTime } from "../lib/utils";
import { Panel, Stat, Badge, Dot, Skeleton, Empty } from "../components/ui";
import { TimeChart, frameMatrix } from "../components/charts";
import { Network, Timer, Activity, Cpu, MemoryStick, ScrollText, ExternalLink } from "lucide-react";

const short = (s) => s.replace("-service", "").replace("-api", "");
const JAEGER = `http://${location.hostname}:16686`;

function svcExpr() {
  return {
    req: 'sum by (service_name) (rate(calls{span_kind="SPAN_KIND_SERVER"}[1m]))',
    p95: 'histogram_quantile(0.95, sum by (le, service_name) (rate(duration_bucket{span_kind="SPAN_KIND_SERVER"}[1m])))',
    cpu: '100 * sum by (job) (rate(process_cpu_time[1m]))',
    mem: 'sum by (job) (process_memory_usage) / 1048576',
  };
}

export default function ServiceMesh() {
  const { data: svcData, isLoading } = useServices();
  const { data: ov } = useOverview();
  const E = svcExpr();
  const req = useMetricsRange(E.req, 15);
  const p95 = useMetricsRange(E.p95, 15);
  const cpu = useMetricsRange(E.cpu, 15);
  const mem = useMetricsRange(E.mem, 15);
  const [logSvc, setLogSvc] = useState("payments-service");
  const { data: logs } = useLogs(logSvc);

  const origin = ov?.is_incident ? ov.root_cause_service : null;
  const reqF = frameMatrix(req.data?.result, (m) => short(m.service_name || ""));
  const p95F = frameMatrix(p95.data?.result, (m) => short(m.service_name || ""));
  const cpuF = frameMatrix(cpu.data?.result, (m) => short(m.job || ""));
  const memF = frameMatrix(mem.data?.result, (m) => short(m.job || ""));

  return (
    <div className="space-y-4">
      {/* service cards */}
      <div className="grid md:grid-cols-3 gap-4">
        {SERVICES.map((s) => {
          const m = svcData?.services?.[s] || {};
          const up = svcData?.health?.[s];
          const isOrigin = origin === s;
          return (
            <Panel key={s} title={s} icon={Network}
              right={<Badge tone={isOrigin ? "red" : up ? "emerald" : "zinc"}>
                <Dot tone={isOrigin ? "red" : up ? "emerald" : "zinc"} />{isOrigin ? "origin" : up ? "healthy" : "down"}</Badge>}
              className={isOrigin ? "ring-1 ring-red-500/40" : ""}>
              <div className="grid grid-cols-2 gap-3">
                {[["p95", fmt(m.lat_p95, 0), "ms", Timer], ["req/s", fmt(m.req_rate, 1), "", Activity],
                  ["cpu", fmt(m.cpu, 2), "cores", Cpu], ["mem", fmt(m.mem_mb, 0), "MB", MemoryStick]].map(([l, v, u, Ic]) => (
                  <div key={l} className="rounded-lg bg-[#141417] px-3 py-2">
                    <div className="flex items-center justify-between"><span className="text-[10px] uppercase text-zinc-500">{l}</span><Ic className="h-3 w-3 text-zinc-600" /></div>
                    <div className="nums mt-0.5 text-[15px] font-medium text-zinc-100">{v}<span className="text-[10px] text-zinc-600"> {u}</span></div>
                  </div>
                ))}
              </div>
              <a href={`${JAEGER}/search?service=${s}`} target="_blank" rel="noreferrer"
                className="mt-3 inline-flex items-center gap-1.5 text-[11px] text-indigo-400 hover:text-indigo-300">
                <ExternalLink className="h-3 w-3" /> traces in Jaeger
              </a>
            </Panel>
          );
        })}
      </div>

      {/* RED time series */}
      <div className="grid lg:grid-cols-2 gap-4">
        <Panel title="Request rate" subtitle="server spans/s by service" icon={Activity}>
          {reqF.rows.length ? <TimeChart rows={reqF.rows} keys={reqF.keys} height={190} /> : <Skeleton className="h-44" />}
        </Panel>
        <Panel title="p95 latency" subtitle="trace-derived, by service" icon={Timer}>
          {p95F.rows.length ? <TimeChart rows={p95F.rows} keys={p95F.keys} height={190} unit="ms" /> : <Skeleton className="h-44" />}
        </Panel>
        <Panel title="CPU" subtitle="% of a core by service" icon={Cpu}>
          {cpuF.rows.length ? <TimeChart rows={cpuF.rows} keys={cpuF.keys} height={170} area={false} /> : <Skeleton className="h-40" />}
        </Panel>
        <Panel title="Memory" subtitle="MB resident by service" icon={MemoryStick}>
          {memF.rows.length ? <TimeChart rows={memF.rows} keys={memF.keys} height={170} area={false} /> : <Skeleton className="h-40" />}
        </Panel>
      </div>

      {/* logs */}
      <Panel title="Live logs" subtitle="Loki" icon={ScrollText}
        right={
          <select value={logSvc} onChange={(e) => setLogSvc(e.target.value)}
            className="rounded-lg border border-edge bg-[#141417] px-2 py-1 text-[12px] text-zinc-300">
            {SERVICES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>}>
        {logs?.logs?.length ? (
          <div className="max-h-72 overflow-y-auto font-mono text-[11px] leading-relaxed space-y-0.5">
            {logs.logs.map((l, i) => {
              let body = l.line;
              try { body = JSON.parse(l.line).body || l.line; } catch { /* raw */ }
              const isErr = /error/i.test(l.line);
              return (
                <div key={i} className="flex gap-2">
                  <span className="text-zinc-600 shrink-0">{tzTime(l.ts)}</span>
                  <span className={isErr ? "text-red-400" : "text-zinc-400"}>{body}</span>
                </div>
              );
            })}
          </div>
        ) : <Empty icon={ScrollText} title="no recent logs" />}
      </Panel>
    </div>
  );
}
