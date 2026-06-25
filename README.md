# Observability & AIOps Platform

**Topic 8 (ANPP-OP) · EduQual Level 6 · Diploma in AI Operations**
Intelligent Monitoring · Root Cause Analysis · Automated Remediation

A self-healing observability stack: a 3-service dependency mesh emits
metrics/logs/traces over OpenTelemetry; an OTel Collector turns traces into
per-service RED metrics; an unsupervised base-model + XGBoost ensemble confirms
incidents and uses per-incident SHAP to name the **origin** service; confirmed
incidents flow through a single Alertmanager plane to an Ansible remediation
engine that fixes the origin service — closing the loop.

> Built strictly from `AIOps_Observability_Implementation_Plan.md` (the single
> source of truth), phase by phase.

## Architecture (5 layers)

```
L1 Traffic    chaos+load generator -> frontend-api -> orders-service -> payments-service
L2 Ingestion  OpenTelemetry Collector (otlp receivers, spanmetrics connector)
L3 Backend    Prometheus | Loki | Jaeger | Grafana | Alertmanager
L4 AI         IsolationForest + PCA + TF Autoencoder  ->  XGBoost + SHAP RCA
L5 Loop       Alertmanager -> webhook -> Ansible -> restart/scale ORIGIN service
              -> if no runbook / fix fails / flapping: EMAIL the SRE team
              + custom React/Tremor AIOps dashboard
```

> **RCA localization** (Fix #4, reworked): the origin is the *deepest service
> whose own fault signature* (latency / errors / cpu / memory — request-rate
> excluded) is elevated above learned-normal. This fixes the previous
> "deepest SHAP-anomalous service" rule, which let a downstream request-rate
> *drop* flip the origin away from an edge fault. Offline hit-rate improved from
> 54.5% to **90–100%** (test-split dependent); **12/12** synthetic service×fault
> combinations localize correctly (`python ai/ensemble/test_rca.py`), and the
> live stack was verified to localize edge faults (frontend) and leaf faults
> (payments) correctly (`python scripts/smoke_test.py`).
>
> **Stability:** the base anomaly models are regularized (small-rank PCA, fewer
> AE epochs) so a benign operating-point shift no longer triggers a false-positive
> baseline, and remediation has a post-restart **cooldown** so a restart's
> transient 5xx can't start a restart storm. When automation can't fix an incident
> (no runbook / failed / flapping) the SRE team is **emailed** (env-driven SMTP).

## Repo layout

| Path | Contents |
|---|---|
| `services/` | `frontend-api`, `orders-service`, `payments-service` |
| `otel/` | OTel Collector config |
| `observability/` | `prometheus/`, `loki/`, `jaeger/`, `grafana/`, `alertmanager/` |
| `chaos/` | load + fault injection + ground-truth label emitter |
| `ai/` | `preprocessor/`, `base_models/`, `ensemble/`, `inference/`, `shap_rca/` |
| `remediation/` | Ansible playbooks (`ansible/`) + Argo alternative (`argo/`) |
| `dashboard/` | React / Tailwind / Tremor app |
| `diagrams/` | network, data-flow, architecture |
| `docs/` | governance, standards-mapping, demo-script, interview-qa |

## Quick start

```bash
cp .env.example .env        # then edit secrets
docker compose up -d        # or: make up
docker compose ps
docker compose down         # or: make down
```

> On Windows hosts without a working `make`, run the wrapped command directly
> (see `Makefile` for the mapping).

## Ports

| URL | Service |
|---|---|
| http://localhost:3002 | **AIOps dashboard** (custom React/Tremor narrative view) |
| http://localhost:3000 | Grafana — lands on **AIOps Platform — Overview** (SLOs, RED, latency heatmap, saturation, logs, alerts); + Service RED & Latency, Resources & Saturation, Logs & Errors drill-downs. `admin` / `$GRAFANA_ADMIN_PASSWORD` |
| http://localhost:9090 | Prometheus · http://localhost:9093 Alertmanager · http://localhost:3100 Loki |
| http://localhost:16686 | Jaeger UI |
| :8001 / :8002 / :8003 | frontend-api / orders-service / payments-service |
| :8080 | remediation engine · :4317/:4318 OTLP |

## Run the demo

The self-healing money-shot (< 2 min) and full runbook: **[docs/demo-script.md](docs/demo-script.md)**.
Needs a **≥ 6-CPU Docker VM** (the unsupervised base models are operating-point sensitive).

## Docs

- [docs/demo-script.md](docs/demo-script.md) — demo runbook
- [docs/standards-mapping.md](docs/standards-mapping.md) — ISO 27001 / NIST / ITIL control points
- [docs/governance.md](docs/governance.md) + [docs/governance-slide.html](docs/governance-slide.html)
- [docs/interview-qa.md](docs/interview-qa.md) — interview answers
- [diagrams/diagrams.md](diagrams/diagrams.md) — network-flow · data-flow · architecture · **self-healing decision-flow** (+ [eraser.io paste-ready versions](diagrams/eraser-diagrams.md))

## ⚠️ Scope, known limitations & threat model

This is a **portfolio / research demonstrator**, not a production deployment. The
end-to-end pipeline is real (telemetry → ensemble ML → RCA → closed-loop
remediation), but the following are deliberately out of scope or known-brittle —
documented here on purpose, because the project's value is a working AIOps loop
you can *reason about*, including where ML-driven remediation breaks and how it is guarded.

**ML / detection**
- **Small, synthetic, class-balanced dataset.** Models train/evaluate on ~50
  chaos-labelled 60 s windows (held-out test n = 20, ≈50/50). Headline numbers
  (PR-AUC, RCA hit-rate) describe that balanced sandbox — **not** production
  incident prevalence (where incidents are ≪1 %). Read them as "works on the demo
  distribution," not a generalisation guarantee. The dashboard labels them `n=20 (synthetic, balanced)`.
- **Operating-point sensitivity.** The unsupervised base models (PCA / autoencoder)
  learn "normal" from a small window set, so the *raw* meta-model probability can read
  high when the live operating point drifts (host RAM pressure, load level) — even when
  nothing is wrong. The **decision**, however, is made by an **adaptive evidence gate**:
  it re-estimates "normal" from a rolling, robust (median / MAD) baseline of recent
  non-incident traffic (`ROLLING_BASELINE`, default on), so legitimate drift is absorbed
  instead of flagged, while a genuine fault still deviates sharply from the *recent*
  baseline. Layered on top: a **same-signature confirmation debounce**, **absolute
  latency / CPU floors** (a drift-proof second gate), an **evidence-scaled display
  probability**, and the **disarmed-by-default** act step. The base models themselves are
  still trained on *absolute* features (so the raw probability is disclosed in the UI,
  not hidden); retraining them on self-normalised features is the remaining step.
- **Auto-remediation is DISARMED by default** (`AUTO_REMEDIATE=false`). Because a
  benign blip can momentarily resemble a real fault, the *act* step (restart) is
  gated behind an explicit arm switch (toggle in the dashboard → Settings).
  Detection + RCA always run; arming enables the closed loop. This is the intended
  **human-in-the-loop / armed-automation** posture and guarantees a healthy service
  is never restarted at idle.

**Security — demo-scoped, do NOT expose to an untrusted network**
- **No authentication/authorization** on the control plane (`:8050`), the
  per-service fault endpoints (`:8001-8003/control/*`), or the remediation webhook
  (`:8080/hook`). All assume a single trusted host.
- **The remediation container mounts the host Docker socket** (`/var/run/docker.sock`)
  to restart origin containers — host-root-equivalent. Fine for a local demo, not
  for shared infrastructure.
- **Backends are unauthenticated and host-bound** (Prometheus remote-write,
  Alertmanager `/api/v2/alerts`, Loki, Jaeger). Set a real `GRAFANA_ADMIN_PASSWORD`
  in `.env`. OTLP is plaintext (no TLS) on the internal network.

**Operations**
- **Single-node, no HA.** One Compose stack; only `aiops-api` has a restart policy.
  Runtime state (incident history, load workers) is in-memory and resets on restart.
- **Reproducibility.** The dashboard build is locked (`package-lock.json` + `npm ci`)
  and trained model artifacts are committed, so `docker compose up -d --build`
  reproduces the demoed system from a clean clone. Python deps are range-pinned
  (`>=x,<y`); a full `pip` lockfile is future work.

## Pre-submission checklist (§5)

- [x] Prometheus **+ Grafana +** Alertmanager present & used (Fix #1)
- [x] Loki logs ingested via OTel Collector
- [x] OpenTelemetry + Jaeger traces flowing
- [x] **`spanmetrics`** producing trace-derived features the model consumes (Fix #3)
- [x] 3-service dependency chain with cascading faults (Fix #5)
- [x] Chaos generator emits **ground-truth labels** (Fix #2)
- [x] XGBoost with imbalance handling + PR-AUC; report saved (`models/ensemble_report.json`)
- [x] **Per-incident SHAP** RCA + quantified hit-rate (Fix #4)
- [x] One Alertmanager plane; **Prometheus pushes**; AI posts; remediation only via webhook (Fix #7)
- [x] Unattended self-healing loop < 2 min
- [x] Custom dashboard **and** Grafana both demoable
- [x] ISO 27001 / NIST / ITIL mapping with concrete controls (Fix #6)
- [x] Three diagrams, consistent, correct alert direction
- [x] Repo: configs, dashboards, AI, automation, diagrams, docs (§4.4 / §11)
- [x] Demo runbook + interview Q&A sheet

## Build status (phase gates)

- [x] **Phase 0** — Foundation & repo scaffolding
- [x] **Phase 1** — 3-service mesh (frontend-api → orders-service → payments-service)
- [x] **Phase 2** — OpenTelemetry instrumentation (traces+metrics+logs over OTLP)
- [x] **Phase 3** — OTel Collector + span metrics (spanmetrics→Prometheus, +Loki +Jaeger)
- [x] **Phase 4** — Grafana (3 datasources + correlation + dashboards) + Alertmanager + threshold rules
- [x] **Phase 5** — Chaos & load generator + ground-truth labels (labels.csv)
- [x] **Phase 6** — Feature engineering (24 per-service features incl. trace-derived latency)
- [x] **Phase 7** — Base models (IsolationForest + PCA + TF autoencoder, normal-only)
- [x] **Phase 8** — XGBoost meta-model + per-incident SHAP RCA
- [x] **Phase 9** — Inference service → single Alertmanager plane (ai-ensemble alerts)
- [x] **Phase 10** — Automated remediation: closed self-healing loop + audit log
- [x] **Phase 11** — Enterprise AIOps dashboard (React/Tailwind/Tremor)
- [x] **Phase 12** — Standards mapping & governance (ISO 27001 / NIST / ITIL)
- [x] **Phase 13** — Three mandatory diagrams (network-flow, data-flow, architecture)
- [x] **Phase 14** — Demo runbook, repo finalisation, interview Q&A
