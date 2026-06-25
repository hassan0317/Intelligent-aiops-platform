async function getJSON(url) {
  const r = await fetch(url, { headers: { Accept: "application/json" } });
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return r.json();
}
async function postJSON(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return r.json();
}

export const api = {
  overview: () => getJSON("/api/overview"),
  aiState: () => getJSON("/api/ai/state"),
  aiHistory: () => getJSON("/api/ai/history"),
  aiModel: () => getJSON("/api/ai/model"),
  services: () => getJSON("/api/services"),
  alerts: () => getJSON("/api/alerts"),
  remediation: () => getJSON("/api/remediation"),
  escalations: () => getJSON("/api/escalations"),
  system: () => getJSON("/api/system"),
  chaosStatus: () => getJSON("/api/chaos/status"),
  scenarioStatus: () => getJSON("/api/chaos/scenario"),
  loadStatus: () => getJSON("/api/load/status"),
  settings: () => getJSON("/api/settings"),
  metricsRange: (expr, minutes = 15, step = 15) =>
    getJSON(`/api/metrics/range?expr=${encodeURIComponent(expr)}&minutes=${minutes}&step=${step}`),
  logs: (service) => getJSON(`/api/logs?limit=40${service ? `&service=${service}` : ""}`),

  inject: (b) => postJSON("/api/chaos/inject", b),
  clear: (b) => postJSON("/api/chaos/clear", b || {}),
  scenario: (b) => postJSON("/api/chaos/scenario", b || {}),
  loadStart: () => postJSON("/api/load/start"),
  loadStop: () => postJSON("/api/load/stop"),
  loadConfig: (workers) => postJSON("/api/load/config", { workers }),
  setSettings: (b) => postJSON("/api/settings", b),
};
