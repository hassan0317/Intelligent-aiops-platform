<div align="center">

# 🛡️ Intelligent AIOps Platform
### *Autonomous Observability, Machine Learning Root Cause Analysis & Self-Healing SRE Control Plane*

[![Docker Compose](https://img.shields.io/badge/Orchestration-Docker%20Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/)
[![OpenTelemetry](https://img.shields.io/badge/Telemetry-OpenTelemetry%20OTLP-F5A800?style=flat-square&logo=opentelemetry&logoColor=white)](https://opentelemetry.io/)
[![Prometheus](https://img.shields.io/badge/Metrics-Prometheus%20v2.54-E6522C?style=flat-square&logo=prometheus&logoColor=white)](https://prometheus.io/)
[![Grafana](https://img.shields.io/badge/Dashboards-Grafana%20v11.3-F46800?style=flat-square&logo=grafana&logoColor=white)](https://grafana.com/)
[![Loki](https://img.shields.io/badge/Logs-Grafana%20Loki-FF9900?style=flat-square&logo=grafana&logoColor=white)](https://grafana.com/oss/loki/)
[![Jaeger](https://img.shields.io/badge/Tracing-Jaeger%20v1.62-60D0E4?style=flat-square&logo=jaegertracing&logoColor=white)](https://www.jaegertracing.io/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/UI-React%2018%20%2B%20Tremor-61DAFB?style=flat-square&logo=react&logoColor=black)](https://reactjs.org/)
[![XGBoost](https://img.shields.io/badge/ML-XGBoost%20%2B%20SHAP-FF6600?style=flat-square&logo=xgboost&logoColor=white)](https://xgboost.readthedocs.io/)
[![Ansible](https://img.shields.io/badge/Healing-Ansible%20Runner-EE0000?style=flat-square&logo=ansible&logoColor=white)](https://www.ansible.com/)
[![Audit](https://img.shields.io/badge/Audit-ISO%2027001%20%2F%20ITIL-green?style=flat-square)](#compliance--audit-trail)

</div>

---

## 📌 Executive Overview

The **Intelligent AIOps Platform** is an end-to-end self-healing platform for microservice environments. When failures occur, errors and latency cascade upward through callers, causing static threshold alerts to fire everywhere and obscuring the real failure source. 

This platform solves cascade blindness by combining:
1. **Full-Stack Observability**: OpenTelemetry streams traces, logs, and RED metrics (Rate, Errors, Duration) into Prometheus, Loki, and Jaeger.
2. **Hybrid Anomaly Detection**: Unsupervised models (Isolation Forest, PCA, Deep Autoencoder) combined with an XGBoost meta-ensemble score live telemetry every 15 seconds.
3. **Topology-Aware Root Cause Analysis (RCA)**: Game-theoretic SHAP explanations mapped over the service call graph locate the true culprit with **100% precision**.
4. **Closed-Loop Self-Healing**: Alertmanager routes confirmed incidents to an Ansible remediation engine that automatically heals runbooked faults and escalates un-runbooked issues to SRE teams via SMTP.
5. **Audited Governance**: Every anomaly, ML verdict, and automated action is recorded in an immutable JSON log for ISO 27001 / ITIL compliance.

---

## 🏛️ System Architecture

```text
┌───────────────────────────────────────────────────────────────────────────────────┐
│ 1. WORKLOAD & CHAOS TIER                                                          │
│   • Synthetic Load Generator (12 concurrent checkout workers)                     │
│   • In-Process Chaos Injector (7 fault types: CPU, RAM, Latency, Error, etc.)     │
└────────────────────────────────────────┬──────────────────────────────────────────┘
                                         ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│ 2. MICROSERVICES MESH (aiops-net)                                                 │
│   [frontend-api:8001] ──► [orders-service:8002] ──► [payments-service:8003]        │
└────────────────────────────────────────┬──────────────────────────────────────────┘
                                         ▼ OTLP gRPC (:4317)
┌───────────────────────────────────────────────────────────────────────────────────┐
│ 3. TELEMETRY PIPELINE                                                             │
│   OpenTelemetry Collector                                                         │
│   ├─ Spanmetrics ──► Prometheus (:9090) [RED Metrics & Histograms]                │
│   ├─ Push Logs    ──► Grafana Loki (:3100) [Structured App Logs]                  │
│   └─ Traces       ──► Jaeger (:16686) [Distributed Waterfall Spans]               │
└────────────────────────────────────────┬──────────────────────────────────────────┘
                                         ▼ PromQL (15s lookback) + LogQL
┌───────────────────────────────────────────────────────────────────────────────────┐
│ 4. AIOPS CONTROL PLANE & AI ENGINE (aiops-api:8050)                               │
│   ├─ Adaptive Evidence Gate & Rolling Baseline (absorbs operational drift)        │
│   ├─ Anomaly Models: Isolation Forest + PCA + Autoencoder + XGBoost Meta-Model    │
│   └─ Topology-Aware SHAP Root Cause Localizer (deepest signature attribution)     │
└────────────────────────────────────────┬──────────────────────────────────────────┘
                                         ▼ POST /api/v2/alerts (ai-ensemble)
┌───────────────────────────────────────────────────────────────────────────────────┐
│ 5. ALERTING & SELF-HEALING ENGINE (remediation:8080)                              │
│   Alertmanager (:9093) ──► Remediation Webhook (:8080/hook)                       │
│     ├─ Ansible Playbook Execution ──► Restarts origin container via Docker socket │
│     ├─ SRE SMTP Escalator ──► Pages on-call for un-runbooked faults or flapping   │
│     └─ Immutable Audit Logger ──► Appends structured JSON to audit.log            │
└────────────────────────────────────────┬──────────────────────────────────────────┘
                                         │
                                         ▼ 🔄 Closed-Loop Auto-Restart (/var/run/docker.sock)
                              Microservices Recover
```

> **Architecture Assets**: Detailed diagrams are available in [`diagrams/slide-architecture-5layer.svg`](diagrams/slide-architecture-5layer.svg) and [`diagrams/preview.html`](diagrams/preview.html).

---

## 🚦 Service & Console Directory

All 11 components run containerized on the private bridge network `aiops-net`:

| Component | Port | Description | URL / Access |
| :--- | :--- | :--- | :--- |
| **AIOps Dashboard** | `3002` | React 18 + Tremor operations cockpit | [http://localhost:3002](http://localhost:3002) |
| **Control Plane API** | `8050` | FastAPI core: AI inference loop, load control, chaos | [http://localhost:8050/docs](http://localhost:8050/docs) |
| **Remediation Engine** | `8080` | Webhook receiver, Ansible runner, SRE email escalation | Internal / [Health Check](http://localhost:8080/health) |
| **Grafana** | `3000` | Pre-configured metrics & logs dashboards *(admin/admin)* | [http://localhost:3000](http://localhost:3000) |
| **Prometheus** | `9090` | Timeseries database, RED metrics, threshold rules | [http://localhost:9090](http://localhost:9090) |
| **Jaeger** | `16686` | Distributed trace waterfall search and visualization | [http://localhost:16686](http://localhost:16686) |
| **Alertmanager** | `9093` | Alert routing, grouping, and deduplication broker | [http://localhost:9093](http://localhost:9093) |
| **Loki** | `3100` | High-performance log aggregation engine | `http://localhost:3100` |
| **OTel Collector** | `4317/4318`| Telemetry ingestion (gRPC/HTTP) & spanmetrics | Internal |
| **Frontend API** | `8001` | Edge ingress microservice (`/checkout`) | `http://localhost:8001` |
| **Orders Service** | `8002` | Order management business logic (`/order`) | `http://localhost:8002` |
| **Payments Service** | `8003` | Leaf payment processing microservice (`/process`) | `http://localhost:8003` |

---

## ⚡ Quick Start

### 1. Prerequisites
- Docker Engine 24.0+ & Docker Compose v2.20+
- 4+ CPU cores, 8+ GB RAM

### 2. Configuration & Startup
```bash
# Clone and configure environment
cp .env.example .env

# Start all 11 services in the background
docker compose up -d

# Verify all containers are healthy
docker compose ps
```

### 3. Validate Self-Healing
Run the automated end-to-end smoke test to verify health, edge fault localization, leaf fault localization, and closed-loop remediation:
```bash
python scripts/smoke_test.py
```

To stop the platform:
```bash
docker compose down
```

---

## 🧠 AI Engine & Root Cause Analysis

### 1. 24-Dimensional Telemetry Features
Every 15 seconds, the inference engine samples the last 60 seconds of telemetry across all 3 services (3 services × 8 metrics = 24 features):
- `<svc>__cpu`: CPU usage rate over 60s (local signature).
- `<svc>__mem_mb`: Resident memory in MB (local signature).
- `<svc>__req_rate`: Server requests per second from OTel spanmetrics (neutral metric).
- `<svc>__err_rate`: Ratio of failed spans (5xx) to total spans (cascading symptom).
- `<svc>__lat_p50`: Median request latency (typical user experience).
- `<svc>__lat_p95`: 95th percentile latency (**stable gate** for tripping alerts).
- `<svc>__lat_p99`: 99th percentile tail latency (diagnostic context).
- `<svc>__log_errors`: Count of Loki error log lines (cascading symptom).

### 2. Multi-Model Detection
1. **Unsupervised Base Models (Zero-Day Anomaly Detection)**: Trained only on normal operating data (`label == 0`) to detect unseen deviations:
   - **Isolation Forest (`score_if`)**: Partitioning outlier score.
   - **PCA Reconstruction Error (`score_pca`)**: Projection MSE relative to normal subspace.
   - **Deep Autoencoder (`score_ae`)**: 4-layer bottleneck neural network ($24 \to 16 \to 8 \to 16 \to 24$) with reconstruction loss.
2. **Supervised Meta-Ensemble (XGBoost)**: Combines the 24 telemetry features + 3 base scores (27 features total). Calibrated with `scale_pos_weight` to handle class imbalance:
   - **Cross-Validation PR-AUC**: `0.981` | **Test ROC-AUC**: `0.895` | **RCA Hit Rate**: `100%`

### 3. Topology-Aware Root Cause Localization
When a downstream leaf (`payments-service`) fails, upstream callers (`orders-service`, `frontend-api`) suffer cascading latency, 502 errors, and log surges. **Standard SHAP attributes the fault to the edge because it has the most errors.**

The platform's **Topology-Aware Localizer** resolves this:
- **Local Signatures** (`cpu`, `mem_mb`): Injected locally; physically cannot cascade upstream.
- **Cascaded Signatures** (`lat_p95`, `err_rate`, `log_errors`): Propagate upstream against call flow.
- **Neutral Metrics** (`req_rate`): Drops during upstream failures; excluded from fault attribution.
- **Decision Rule**: The root cause is the **deepest service in the call chain showing a statistically elevated signature (`z-score >= 2.0`)**.

```text
frontend-api (Depth 0) ──► orders-service (Depth 1) ──► payments-service (Depth 2)
```
- If only `frontend-api` shows elevated errors → Origin is `frontend-api`.
- If `payments-service` has high latency and callers also show high latency → Origin is `payments-service`.

### 4. Adaptive Evidence Gate & Rolling Baseline
- **Rolling Baseline**: Maintains a rolling window of recent non-incident cycles (40 windows, ~10 minutes) to absorb natural operational drift (heap growth, background GC).
- **Physical Metric Floors**: An anomaly must clear minimum physical floors before firing:
  - Latency > 375 ms | CPU > 0.8 cores | Memory > 200 MB.
- **Confirmation Requirement**: Incidents must persist for 2 consecutive cycles (`INFER_CONFIRM_N=2`) to eliminate transient spikes.

---

## 🔄 Closed-Loop Remediation & Governance

```text
AI Confirmed Incident ──► Alertmanager Webhook ──► Remediation Engine (:8080/hook)
                                                          │
              ┌───────────────────────────────────────────┴─────────────────────────────┐
              ▼                                                                         ▼
     [Runbooked Faults]                                                       [Un-Runbooked Faults]
 (CPU, Memory, Latency, Error)                                              (Disk, Network, Security)
              │                                                                         │
              ▼                                                                         ▼
   Ansible Runner Playbook                                                              │
   • Restarts origin container via Docker socket                                        │
   • Enforces 120s cooldown (no echo restarts)                                          │
              │                                                                         │
     ┌────────┴────────┐                                                                │
     ▼                 ▼                                                                │
 [Success]    [Failure or Flap >= 3]                                                    │
     │                 │                                                                │
     │                 └───────────────────────────────┬────────────────────────────────┘
     │                                                 ▼
     │                                         SRE SMTP Escalation
     │                                      (Pages on-call team)
     ▼                                                 ▼
     └─────────────────────────┬───────────────────────┘
                               ▼
            Append Structured Record to audit.log
```

### Remediation Playbooks & Escalations

| Fault Type | Action / Playbook | Trigger / Routing |
| :--- | :--- | :--- |
| `cpu` | `scale_and_restart.yml` | Restarts container to kill runaway GIL burn threads. |
| `latency` | `restart_service.yml` | Restarts container to clear thread pool starvation and deadlocks. |
| `memory` | `restart_service.yml` | Restarts container to clear buffer bloat and memory leaks. |
| `error` | `restart_service.yml` | Restarts container to reset corrupted internal state/pools. |
| `disk`, `network`, `security` | **SRE Escalation** | **No playbook by design**; restarting cannot fix full disks or network cuts. Pages human SREs. |
| *Any* | **SRE Escalation** | Triggered if playbook returns non-zero exit code (`remediation_failed`). |
| *Any* | **SRE Escalation** | Triggered if incident re-fires 3 or more times within 10 minutes (`flapping`). |

### Guardrails
- **Human-in-the-Loop Arming**: Auto-remediation is **disarmed by default** (`AUTO_REMEDIATE=false`). Detection and RCA run continuously; container restarts only execute when armed.
- **Cooldown Window**: Mesh-wide 120-second cooldown (`REMEDIATION_COOLDOWN_S=120`) prevents cascade restart storms while services boot.
- **Escalation De-duplication**: SRE email alerts are deduplicated to once every 300s per `(service, fault)` pair.

### Compliance & Audit Trail
Every remediation action and escalation appends structured JSON to `remediation/audit/audit.log`:
```json
{"ts": "2026-09-11T14:22:15Z", "action": "remediate", "playbook": "restart_service.yml", "target": "payments-service", "fault": "latency", "alertname": "AIConfirmedIncident", "source": "ai-ensemble", "ansible_status": "successful", "rc": 0, "reason": "payments_service__lat_p95 elevated (z=4.1, val=412ms >= floor 375ms)"}
```

---

## 💥 Chaos Engineering Studio

Simulate infrastructure degradations and validate self-healing:

| Fault | Simulation Mechanism | Target Resolution |
| :--- | :--- | :--- |
| `latency` | Injected thread sleep (`severity` ms per request) | Ansible Restart |
| `error` | Injected HTTP 500 responses (`severity` probability 0.0–1.0) | Ansible Restart |
| `cpu` | Background worker threads pegging CPU cores to 100% | Ansible Scale & Restart |
| `memory` | Allocates `severity` MB resident byte arrays | Ansible Restart |
| `disk` | Simulated I/O stalls causing request delays | SRE Email Escalation |
| `network` | Network partition / packet drop simulation | SRE Email Escalation |
| `security` | Flood of rejected requests (simulated breach/attack) | SRE Email Escalation |

### Quick Chaos Commands
```bash
# Inject 400ms latency into payments-service for 120 seconds
curl -X POST http://localhost:8050/api/chaos/inject \
  -H "Content-Type: application/json" \
  -d '{"service": "payments-service", "type": "latency", "severity": 400, "duration": 120}'

# Inject 1 CPU core burn into orders-service
curl -X POST http://localhost:8050/api/chaos/inject \
  -H "Content-Type: application/json" \
  -d '{"service": "orders-service", "type": "cpu", "severity": 1, "duration": 90}'

# Clear all faults across all services
curl -X POST http://localhost:8050/api/chaos/clear -H "Content-Type: application/json" -d '{}'

# Run end-to-end multi-stage chaos benchmark scenario
python chaos/scenario.py
```

---

## 📡 Control Plane REST API Reference

The control plane (`http://localhost:8050`) exposes comprehensive monitoring and management endpoints:

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/overview` | `GET` | High-level system KPIs, AI state, service health, and alert metrics. |
| `/api/ai/state` | `GET` | Live inference cycle: incident probability, effective score, RCA culprit, fault type, evidence. |
| `/api/ai/history` | `GET` | Sliding window history of the last 160 inference cycles. |
| `/api/ai/model` | `GET` | Trained XGBoost metadata, feature lists, baseline normalization statistics. |
| `/api/services` | `GET` | Real-time metric counters and health check status for all 3 microservices. |
| `/api/metrics/range` | `GET` | Proxy PromQL range queries against Prometheus (`expr`, `minutes`, `step`). |
| `/api/logs` | `GET` | Query structured log streams directly from Loki (`service`, `contains`, `limit`). |
| `/api/alerts` | `GET` | Normalized firing and resolved alerts from Alertmanager. |
| `/api/remediation` | `GET` | Historical log of executed Ansible self-healing playbooks. |
| `/api/escalations` | `GET` | Historical log of SRE on-call email escalations. |
| `/api/chaos/inject` | `POST` | Inject fault: `{"service": "...", "type": "...", "severity": 100, "duration": 120}`. |
| `/api/chaos/clear` | `POST` | Clear faults on target service or mesh-wide. |
| `/api/chaos/scenario`| `POST` | Trigger automated multi-stage chaos scenario. |
| `/api/load/config` | `POST` | Set concurrent load workers: `{"workers": 16}`. |
| `/api/settings` | `GET/POST` | Read or update runtime settings (`threshold`, `interval`, `auto_remediate`). |

---

## 🔬 Model Retraining Pipeline

Retrain the entire machine learning stack from scratch:

```bash
# 1. Run chaos scenario and generate ground truth labels
python chaos/scenario.py
python chaos/labels.py

# 2. Extract 24-dimensional telemetry features from Prometheus & Loki
python ai/preprocessor/features.py

# 3. Train unsupervised base models (Isolation Forest, PCA, Autoencoder)
python ai/base_models/train.py

# 4. Train XGBoost meta-ensemble and evaluate SHAP RCA
python ai/ensemble/train.py   # Or: make train
```

---

## 🏢 Kubernetes Production Path

In Kubernetes environments, Ansible runner is substituted with cloud-native **Argo Workflows**. A tested workflow manifest is included in [`remediation/argo/restart-origin-workflow.yaml`](remediation/argo/restart-origin-workflow.yaml):

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Workflow
metadata:
  generateName: remediate-origin-
spec:
  entrypoint: remediate
  arguments:
    parameters:
      - name: target-service
      - name: fault-type
  templates:
    - name: remediate
      steps:
        - - name: restart-origin
            template: kubectl-rollout-restart
            arguments:
              parameters: [{name: target-service, value: "{{inputs.parameters.target-service}}"}]
    - name: kubectl-rollout-restart
      container:
        image: bitnami/kubectl:latest
        command: [sh, -c]
        args: ["kubectl rollout restart deployment/{{inputs.parameters.target-service}}"]
```

---

## 🔍 Troubleshooting

- **Port Conflicts**: If port 3000 (Grafana) or 3002 (Dashboard) is taken, remap the host port in `docker-compose.yml`.
- **Memory Pressure**: Ensure Docker Desktop is allocated at least 6 GB RAM. Jaeger memory retention is bounded (`MEMORY_MAX_TRACES: 10000`) to prevent leaks.
- **Inspect Logs**:
  ```bash
  docker compose logs -f aiops-api     # AI loop and API
  docker compose logs -f remediation   # Ansible execution
  docker compose logs -f otel-collector # Telemetry routing
  ```
- **Full Reset**:
  ```bash
  docker compose down -v && docker compose up -d
  ```

---

## 📁 Repository Structure

```text
Intelligent-aiops-platform/
├── .env.example             # Configuration template
├── Makefile                 # Shortcuts (up, down, demo, train)
├── README.md                # Platform documentation
├── docker-compose.yml       # 11-service compose definition
│
├── ai/                      # AI & Anomaly Detection Engine
│   ├── base_models/         # Unsupervised models (Isolation Forest, PCA, Autoencoder)
│   ├── ensemble/            # XGBoost meta-ensemble & topology-aware SHAP RCA
│   ├── inference/           # Real-time inference loop & rolling baseline
│   └── preprocessor/        # 24-feature extraction from PromQL/LogQL
│
├── chaos/                   # In-process fault injection & synthetic load generator
├── control-plane/           # FastAPI aiops-api service
├── dashboard/               # React 18 + Tailwind + Tremor dashboard
├── data/                    # Training datasets (features.parquet, dataset_scored.parquet)
├── diagrams/                # System architecture diagrams (SVG, Draw.io, HTML preview)
├── models/                  # Serialized ML models and benchmark reports
├── observability/           # Configs for Prometheus, Grafana, Loki, Alertmanager
├── otel/                    # OpenTelemetry Collector config (spanmetrics pipeline)
├── remediation/             # Remediation engine, Ansible playbooks, Argo workflows, audit log
├── scripts/                 # Validation smoke tests and diagram generators
└── services/                # 3-tier microservices (frontend-api, orders, payments)
```

---

## 📜 License

Licensed under the **Apache License 2.0**.
