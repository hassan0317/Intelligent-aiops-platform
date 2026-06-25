# Observability & AIOps Platform

An end-to-end AIOps platform that combines observability, anomaly detection, root cause analysis, and automated remediation in a single self-healing workflow.

The platform monitors a distributed microservice environment using metrics, logs, and traces collected through OpenTelemetry. Telemetry is analyzed by an AI engine that detects abnormal behavior, identifies the most likely source of failure, and can automatically trigger remediation actions.

---

## Architecture

```text
Load & Fault Generation
          │
          ▼
┌─────────────────────────────────┐
│        Microservices            │
│ frontend → orders → payments    │
└─────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────┐
│     OpenTelemetry Collector     │
└─────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────┐
│ Prometheus │ Loki │ Jaeger      │
└─────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────┐
│            AI Engine            │
│ Isolation Forest                │
│ PCA                             │
│ Autoencoder                     │
│ XGBoost + SHAP RCA              │
└─────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────┐
│ Alertmanager → Remediation      │
│            Engine               │
└─────────────────────────────────┘
          │
          ▼
      Self-Healing
```

---

## Technology Stack

### Backend

* Python
* FastAPI
* Docker
* Docker Compose

### Observability

* OpenTelemetry
* Prometheus
* Grafana
* Loki
* Jaeger
* Alertmanager

### Machine Learning

* Scikit-learn
* TensorFlow
* XGBoost
* SHAP

### Automation

* Ansible

### Frontend

* React
* Tailwind CSS
* Tremor

---

## Project Structure

```text
.
├── ai/                          # AI engine
│   ├── preprocessor/
│   ├── base_models/
│   ├── ensemble/
│   ├── inference/
│   └── shap_rca/
│
├── services/                    # Application services
│   ├── frontend-api/
│   ├── orders-service/
│   └── payments-service/
│
├── observability/               # Monitoring stack
│   ├── prometheus/
│   ├── grafana/
│   ├── loki/
│   ├── jaeger/
│   └── alertmanager/
│
├── otel/                        # OpenTelemetry Collector
├── chaos/                       # Load & fault injection
├── remediation/                 # Automated remediation
├── dashboard/                   # React dashboard
├── control-plane/               # Platform APIs
├── data/                        # Feature datasets
├── models/                      # Trained models
├── scripts/                     # Utilities & tests
├── diagrams/                    # Architecture diagrams
├── secrets/                     # Local secrets
│
├── docker-compose.yml
├── Makefile
└── README.md
```

---

## Services

| Service            | Port        |
| ------------------ | ----------- |
| Dashboard          | 3002        |
| Grafana            | 3000        |
| Prometheus         | 9090        |
| Alertmanager       | 9093        |
| Loki               | 3100        |
| Jaeger             | 16686       |
| Frontend API       | 8001        |
| Orders Service     | 8002        |
| Payments Service   | 8003        |
| OTel Collector     | 4317 / 4318 |
| Remediation Engine | 8080        |

---

## Quick Start

Clone the repository and start the platform:

```bash
cp .env.example .env
docker compose up -d
```

Verify services:

```bash
docker compose ps
```

Stop the platform:

```bash
docker compose down
```

---

## Features

* Metrics, logs, and distributed tracing
* OpenTelemetry-based instrumentation
* Prometheus monitoring and alerting
* Grafana dashboards
* Loki log aggregation
* Jaeger trace visualization
* AI-driven anomaly detection
* Root cause analysis with SHAP explanations
* Automated remediation workflows
* Incident audit logging
* Custom AIOps dashboard

---

## Documentation

Additional documentation is available in the `docs/` directory:

* Architecture diagrams
* Demo guide
* Governance documentation
* Standards mapping
* Interview preparation material
