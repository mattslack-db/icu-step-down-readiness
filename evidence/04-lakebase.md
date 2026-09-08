# Phase 4 Evidence — Lakebase Operational Serving

Date: 2026-09-08

---

## 1. Lakebase Project Status

```
databricks postgres list-projects --profile icu-sandbox
```

| Field | Value |
|-------|-------|
| Project ID | `icu-step-down` |
| Display name | ICU Step-Down Readiness |
| Owner | matt.slack@databricks.com |
| Postgres version | 17 |
| UID | 4dfacebf-2d5c-42fa-a40a-9699151627e1 |
| Created | 2026-09-08T09:33:17Z |

### Branch

| Field | Value |
|-------|-------|
| Branch ID | `production` |
| Path | `projects/icu-step-down/branches/production` |
| State | READY |
| UID | br-solitary-block-d1o8ndlg |

### Primary Endpoint

| Field | Value |
|-------|-------|
| Endpoint ID | `primary` |
| Path | `projects/icu-step-down/branches/production/endpoints/primary` |
| Type | ENDPOINT_TYPE_READ_WRITE |
| State | ACTIVE |
| Host | `ep-floral-cake-d1qay1ix.database.us-west-2.cloud.databricks.com` |
| Pooled host | `ep-floral-cake-d1qay1ix-pooler.database.us-west-2.cloud.databricks.com` |
| Min CU / Max CU | 1 / 1 |
| UID | ep-floral-cake-d1qay1ix |

### Default Database

| Field | Value |
|-------|-------|
| Database ID | `databricks-postgres` |
| Path | `projects/icu-step-down/branches/production/databases/databricks-postgres` |
| Postgres database name | `databricks_postgres` |

---

## 2. Unity Catalog Registration

The Lakebase branch `production` was registered as UC catalog `mimic_iii`:

```
databricks postgres create-catalog mimic_iii \
  --json '{"spec": {"postgres_database": "databricks_postgres", "branch": "projects/icu-step-down/branches/production"}}' \
  --profile icu-sandbox
```

| Field | Value |
|-------|-------|
| UC Catalog name | `mimic_iii` |
| Postgres database | `databricks_postgres` |
| Branch | `projects/icu-step-down/branches/production` |
| UID | b2d6531d-4029-4544-a12f-5b768bd57759 |

---

## 3. Source Table — census_vitals Helper

The full `icu_step_down.silver.vital_signs` table has 21.7M rows — too large for a demo sync.
A scoped gold table was created containing only vitals for the 40 icustay_ids in `gold.census`:

```sql
CREATE TABLE icu_step_down.gold.census_vitals AS
SELECT
    CAST(ROW_NUMBER() OVER (ORDER BY vs.icustay_id, vs.charttime, vs.vital_name)
         AS BIGINT) AS row_id,
    vs.icustay_id,
    vs.subject_id,
    vs.charttime,
    vs.vital_name,
    vs.value
FROM icu_step_down.silver.vital_signs vs
JOIN icu_step_down.gold.census c ON vs.icustay_id = c.icustay_id
```

Row count: 711. Note: the natural composite key `(icustay_id, charttime, vital_name)` has
2 duplicate combinations; a synthetic `row_id` (BIGINT, monotonic) is used as the primary key.

---

## 4. Synced Tables

All three tables created with `SNAPSHOT` scheduling.  
Storage catalog for DLT metadata: `icu_step_down.gold` (a regular UC catalog/schema, not the Lakebase one).  
Postgres schema: `mimic_iii`.

### 4a. census

| Field | Value |
|-------|-------|
| Synced table ID | `mimic_iii.mimic_iii.census` |
| UID | 7b6ad319-0e3d-4f0f-9eb8-bc93bc016db8 |
| Source | `icu_step_down.gold.census` |
| Primary key | `icustay_id` |
| Scheduling | SNAPSHOT |
| DLT Pipeline ID | 85b37fa8-897d-4417-ba95-5bcb1922ce43 |
| Sync state | **SYNCED_TABLE_ONLINE_NO_PENDING_UPDATE** |
| UC provisioning | ACTIVE |

### 4b. patient_features

| Field | Value |
|-------|-------|
| Synced table ID | `mimic_iii.mimic_iii.patient_features` |
| UID | 19640bd3-e337-456c-876c-28b6fddce5f9 |
| Source | `icu_step_down.gold.patient_features` |
| Primary key | `icustay_id` |
| Scheduling | SNAPSHOT |
| DLT Pipeline ID | e2c33fff-c0a8-4e93-be87-76dec3549600 |
| Sync state | **SYNCED_TABLE_ONLINE_NO_PENDING_UPDATE** |
| UC provisioning | ACTIVE |

### 4c. census_vitals

| Field | Value |
|-------|-------|
| Synced table ID | `mimic_iii.mimic_iii.census_vitals` |
| UID | ff6b1fc9-5958-43a0-b3c7-17349f1af4b8 |
| Source | `icu_step_down.gold.census_vitals` |
| Primary key | `row_id` (synthetic BIGINT) |
| Scheduling | SNAPSHOT |
| DLT Pipeline ID | ff636158-966b-4dfa-b958-55cba42ad9e0 |
| Sync state | **SYNCED_TABLE_ONLINE_NO_PENDING_UPDATE** |
| UC provisioning | ACTIVE |

---

## 5. Connection Confirmation

Connected via psycopg 3.3.2:

```python
import psycopg, socket

HOST = "ep-floral-cake-d1qay1ix.database.us-west-2.cloud.databricks.com"
TOKEN = <generated via `databricks postgres generate-database-credential`>
USER = "matt.slack@databricks.com"   # Databricks workspace email

host_ip = socket.getaddrinfo(HOST, 5432, 0, socket.SOCK_STREAM)[0][4][0]

conn = psycopg.connect(
    host=HOST, hostaddr=host_ip,
    user=USER, dbname="databricks_postgres",
    password=TOKEN, sslmode="require"
)
```

> **macOS DNS note:** `socket.getaddrinfo()` fails on long hostnames on macOS.
> Pass both `host=` (for TLS SNI) and `hostaddr=<resolved_ip>` to work around this.

> **Username:** Use the workspace email address (e.g. `matt.slack@databricks.com`),
> not the role ID slug (e.g. `matt-slack`). The role path in the API response uses the
> slug but Postgres authentication requires the full email.

---

## 6. Verification Queries

### Tables in mimic_iii schema

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'mimic_iii'
ORDER BY table_name;
```

**Output:**
```
  census
  census_vitals
  patient_features
```

### Row Counts

```sql
SELECT COUNT(*) FROM mimic_iii.census;          -- => 40  ✓ matches UC gold
SELECT COUNT(*) FROM mimic_iii.patient_features; -- => 61532  ✓ matches UC gold
SELECT COUNT(*) FROM mimic_iii.census_vitals;    -- => 16045  (scoped from 21.7M)
```

**Note (Phase 2 amendment, 2026-09-08):** `census` and `census_vitals` were refreshed to
reflect the updated `gold.census` definition (vitals-populated stays only). The census
MV was recreated via pipeline; `gold.census_vitals` was dropped and recreated (DROP +
CREATE AS SELECT); both synced tables were deleted and recreated via `sync_tables.py`.
Verification confirms `mimic_iii.census` has 40 rows with 40/40/40 hr_mean / spo2_mean /
gcs_last populated. `census_vitals` grew from 711 to 16,045 rows because the new census
stays have extensive vital charting (vs. the prior short-stay population).

### Case-Sensitive Column Sample — census

Lakebase Postgres is case-sensitive. Columns synced from UC Delta tables are
**lowercase**. Queries must double-quote column names to avoid ambiguity
(unquoted identifiers fold to lowercase in Postgres 17, which works here, but
explicit quoting is recommended for correctness):

```sql
SELECT "icustay_id", "subject_id", "hadm_id", "los", "age",
       "on_vasopressors", "on_ventilator"
FROM mimic_iii.census
ORDER BY "icustay_id"
LIMIT 5;
```

**Output:**
```
Columns: ['icustay_id', 'subject_id', 'hadm_id', 'los', 'age', 'on_vasopressors', 'on_ventilator']
  ('200696', '20816', '186333', '10.943', Decimal('63.967146'), False, True)
  ('202836', '25115', '119787', '.8452',  Decimal('78.255989'), False, False)
  ('203462', '24562', '166275', '2.2506', Decimal('45.869952'), False, False)
  ('203874', '5196',  '106963', '4.8772', Decimal('90.000000'), False, True)
  ('204086', '18250', '183165', '1.0476', Decimal('74.584531'), False, False)
```

### Sample from census_vitals

```sql
SELECT "row_id", "icustay_id", "charttime", "vital_name", "value"
FROM mimic_iii.census_vitals
ORDER BY "row_id"
LIMIT 5;
```

**Output:**
```
  (1, '219673', 2206-06-02 17:00:00+00:00, 'dbp', '75')
  (2, '219673', 2206-06-02 17:00:00+00:00, 'gcs', '15')
  (3, '219673', 2206-06-02 17:00:00+00:00, 'hr',  '74')
  (4, '219673', 2206-06-02 17:00:00+00:00, 'rr',  '15')
  (5, '219673', 2206-06-02 17:00:00+00:00, 'sbp', '109')
```
