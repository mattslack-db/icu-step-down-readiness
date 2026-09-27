# icu-step-down ✨

> A modern full-stack application built with [`apx`](https://github.com/databricks-solutions/apx) 🚀

> **This app is one layer of the ICU Step-Down Readiness build.** The overall
> project (Lakeflow pipeline, Unity Catalog gold, Mosaic AI serving, Genie,
> Lakebase, and this app) is documented in the repo root. See **[`../README.md`](../README.md)**
> and, for readable **execution evidence** (committed verbatim run output —
> pipeline row counts, gold query results, a real served prediction, Genie Q&A,
> app RUNNING status), **[`../EVIDENCE.md`](../EVIDENCE.md)** and **[`../evidence/raw/`](../evidence/raw/)**.

## ✅ This build actually ran (readable execution evidence)

Full output: top-level [`../logs/`](../logs/) (`.log` / `.csv` / `.json` / `.md` + a [notebook with cell outputs](../logs/execution-evidence.ipynb)), [`../EVIDENCE.md`](../EVIDENCE.md), and raw [`../evidence/raw/`](../evidence/raw/). Headline results, as committed text:

- **Lakeflow pipeline — COMPLETED**: bronze `chart_events 38,776,289` / `admissions 58,976` → gold `patient_features 61,532`, `census 40`.
- **Gold query** (`icu_step_down.gold.census`): 40 current patients, avg LOS 2.83d, 8 on pressors / 11 on ventilator.
- **Served prediction** (Mosaic AI `icu-readiness`, model v2): `readiness_score 0.4739`, factors `lactate_last (risk 0.262)`, `on_ventilator (risk 0.030)` — ventilator forced to **risk** (safety override, live).
- **Genie Q&A**: *"How many current ICU patients are ready for step-down?"* → generated SQL → `ready=38, not_ready=2, total=40`.
- **App RUNNING** at the deployed URL; Lakebase synced tables ONLINE; drift job PSI 2.15 / KS 0.22; unit-access scoped predicate → 15 MICU rows live.

## 🔬 Data journey & Genie config (readable transformation logic)

Full end-to-end medallion logic + Genie space config: **[`../DATA-JOURNEY.md`](../DATA-JOURNEY.md)**
(source: [`../src/pipelines/`](../src/pipelines/) `bronze.sql`/`silver.sql`/`gold.sql`,
[`../src/genie/space_config.md`](../src/genie/space_config.md)). In brief:

- **Bronze**: Delta-shared MIMIC-III tables → UC materialized views (raw).
- **Silver**: `chart_events` **unpivoted** to a long `vital_signs` stream via `CASE ITEMID → vital_name` (hr/sbp/dbp/spo2/temp_c/rr), °F→°C conversion, and physiologic range filters; `lab_events` gets an `is_lactate` flag.
- **Gold `patient_features`** (one row/stay): a 24h window per stay → vitals `mean/min/max/last`; `on_vasopressors`/`on_ventilator` from intervention-table ITEMID sets (MetaVision ∪ CareVue); `lactate_last`; derived `recent_extubation` + `active_bleeding`; synthetic `care_unit`. → `readiness_training_set` (+ `readiness_label` = 72h bounce-back) and `census` (40 current).
- **Genie space** exposes `gold.census`, `gold.readiness_training_set`, `silver.vital_signs` with text instructions (disambiguation, data-quality, aggregates-only) and 5 example queries; live Q&A in [`../evidence/raw/genie-qa.txt`](../evidence/raw/genie-qa.txt).

## 🛠️ Tech Stack

This application leverages a powerful, modern tech stack:

- **Backend** 🐍 Python + [FastAPI](https://fastapi.tiangolo.com/)
- **Frontend** ⚛️ React + [shadcn/ui](https://ui.shadcn.com/)
- **API Client** 🔄 Auto-generated TypeScript client from OpenAPI schema

## 🚀 Quick Start

### Development Mode

Start all development servers (backend, frontend, and OpenAPI watcher) in detached mode:

```bash
apx dev start
```

This will start an apx development server, which in it's turn runs backend, frontend and OpenAPI watcher.
All servers run in the background, with logs kept in-memory of the apx dev server.

### 📊 Monitoring & Logs

```bash
# View all logs
apx dev logs

# Stream logs in real-time
apx dev logs -f

# Check server status
apx dev status

# Stop all servers
apx dev stop
```

## ✅ Code Quality

Run type checking and linting for both TypeScript and Python:

```bash
apx dev check
```

## 📦 Build

Create a production-ready build:

```bash
apx build
```

## 🚢 Deployment

Deploy to Databricks:

```bash
databricks bundle deploy -p <your-profile>
```

---

<p align="center">Built with ❤️ using <a href="https://github.com/databricks-solutions/apx">apx</a></p>
