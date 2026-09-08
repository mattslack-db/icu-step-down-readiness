"""
Lakebase Synced Tables — ICU Step-Down Readiness
=================================================

Creates the Lakebase Postgres Autoscaling project `icu-step-down` and syncs
three Unity Catalog gold tables into it as Postgres tables for low-latency
app reads.

DABs Decision
-------------
Neither the Lakebase project nor its synced tables are currently DAB-manageable:
  - `synced_database_tables` in DABs maps to a deprecated Terraform resource
    (`databricks_database_synced_database_table`) that fails on current Lakebase.
  - `postgres_synced_tables` DAB support is blocked on Terraform provider work and
    not yet available (as of Databricks CLI v1.11.0).
This script uses the Databricks CLI (`databricks postgres ...`) directly, which
is the current recommended approach per the `databricks-lakebase` skill.

Idempotency
-----------
Each step checks existence before creating:
  - Lists projects — skips create if `icu-step-down` already exists.
  - Lists UC catalogs — skips `create-catalog` if `mimic_iii` already exists.
  - Checks synced table status — skips `create-synced-table` if already present.

Source tables
-------------
  icu_step_down.gold.census          (40 rows)          PK: icustay_id
  icu_step_down.gold.patient_features (61,532 rows)     PK: icustay_id
  icu_step_down.gold.census_vitals   (711 rows)         PK: row_id (synthetic)

census_vitals is a scoped helper table created in UC gold before syncing:
  CREATE TABLE icu_step_down.gold.census_vitals AS
  SELECT
    CAST(ROW_NUMBER() OVER (ORDER BY vs.icustay_id, vs.charttime, vs.vital_name)
         AS BIGINT) AS row_id,
    vs.icustay_id, vs.subject_id, vs.charttime, vs.vital_name, vs.value
  FROM icu_step_down.silver.vital_signs vs
  JOIN icu_step_down.gold.census c ON vs.icustay_id = c.icustay_id

Rationale: vital_signs has 21.7M rows. Scoping to the 40 census icustay_ids
gives 711 rows — sufficient for the patient-detail vitals chart while avoiding
an oversized sync for a demo workload. The natural composite key
(icustay_id, charttime, vital_name) has 2 duplicates, so a synthetic row_id
is used as the primary key.

Target Postgres location
------------------------
  UC catalog    : mimic_iii   (registered from Lakebase branch production)
  Postgres DB   : databricks_postgres  (default)
  Postgres schema: mimic_iii
  Tables        : census, patient_features, census_vitals

DLT pipeline metadata (storage_catalog/storage_schema)
-------------------------------------------------------
  Uses `icu_step_down.gold` — a regular UC catalog/schema, NOT the Lakebase
  catalog. Per skill guidance: `storage_catalog` must be a regular UC catalog.

Usage
-----
  python src/lakebase/sync_tables.py --profile icu-sandbox [--wait]

  --profile  Databricks CLI profile (default: icu-sandbox)
  --wait     Block until all synced tables reach ONLINE state (default: no-wait)
"""

import argparse
import json
import subprocess
import sys
import time
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROFILE = "icu-sandbox"
PROJECT_ID = "icu-step-down"
BRANCH_ID = "production"
BRANCH_PATH = f"projects/{PROJECT_ID}/branches/{BRANCH_ID}"
LAKEBASE_UC_CATALOG = "mimic_iii"
POSTGRES_DATABASE = "databricks_postgres"
POSTGRES_SCHEMA = "mimic_iii"
STORAGE_CATALOG = "icu_step_down"
STORAGE_SCHEMA = "gold"
PROJECT_DISPLAY_NAME = "ICU Step-Down Readiness"

SYNCED_TABLES = [
    {
        "target": f"{LAKEBASE_UC_CATALOG}.{POSTGRES_SCHEMA}.census",
        "source": "icu_step_down.gold.census",
        "primary_key_columns": ["icustay_id"],
    },
    {
        "target": f"{LAKEBASE_UC_CATALOG}.{POSTGRES_SCHEMA}.patient_features",
        "source": "icu_step_down.gold.patient_features",
        "primary_key_columns": ["icustay_id"],
    },
    {
        "target": f"{LAKEBASE_UC_CATALOG}.{POSTGRES_SCHEMA}.census_vitals",
        "source": "icu_step_down.gold.census_vitals",
        "primary_key_columns": ["row_id"],
    },
]

ONLINE_STATE = "SYNCED_TABLE_ONLINE_NO_PENDING_UPDATE"
POLL_INTERVAL_S = 30
MAX_WAIT_S = 1800  # 30 minutes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run(cmd: list[str], capture: bool = True) -> dict[str, Any] | str:
    """Run a CLI command and return parsed JSON or raw stdout."""
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    if capture and result.stdout.strip():
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return result.stdout
    return {}


def cli(*args: str, json_flag: bool = True) -> dict[str, Any] | str:
    """Build a `databricks postgres ...` command and run it."""
    cmd = ["databricks", "postgres", *args, "--profile", PROFILE]
    if json_flag:
        cmd += ["-o", "json"]
    return run(cmd)


def project_exists() -> bool:
    projects = cli("list-projects") or []
    return any(p.get("project_id") == PROJECT_ID for p in projects)


def catalog_exists() -> bool:
    result = subprocess.run(
        ["databricks", "catalogs", "list", "--profile", PROFILE, "-o", "json"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            f"  ERROR: 'databricks catalogs list' failed (rc={result.returncode}):\n"
            f"  {result.stderr.strip()}",
            file=sys.stderr,
        )
        sys.exit(1)
    catalogs = json.loads(result.stdout) if result.stdout.strip() else []
    return any(c.get("name") == LAKEBASE_UC_CATALOG for c in catalogs)


def synced_table_exists(target: str) -> bool:
    """Return True if the synced table exists, False if genuinely not found.

    Any non-zero exit that is NOT a recognisable "not found" error is treated
    as a hard failure (auth/network/unexpected), not a missing table.
    """
    result = subprocess.run(
        [
            "databricks",
            "postgres",
            "get-synced-table",
            f"synced_tables/{target}",
            "--profile",
            PROFILE,
            "-o",
            "json",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return True
    # Treat only genuine "resource not found" as False.
    stderr_lower = result.stderr.lower()
    not_found_signals = (
        "resource_does_not_exist",
        "does not exist",
        "not found",
        "404",
    )
    if any(sig in stderr_lower for sig in not_found_signals):
        return False
    # Any other non-zero exit (auth failure, network error, …) is a real error.
    print(
        f"  ERROR: 'get-synced-table {target}' failed unexpectedly "
        f"(rc={result.returncode}):\n  {result.stderr.strip()}",
        file=sys.stderr,
    )
    sys.exit(1)


def synced_table_state(target: str) -> str:
    result = cli("get-synced-table", f"synced_tables/{target}")
    return result.get("status", {}).get("detailed_state", "UNKNOWN")


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


def ensure_project() -> None:
    if project_exists():
        print(f"  Project {PROJECT_ID!r} already exists — skipping create.")
        return
    print(f"  Creating Lakebase project {PROJECT_ID!r} ...")
    run(
        [
            "databricks",
            "postgres",
            "create-project",
            PROJECT_ID,
            "--json",
            json.dumps({"spec": {"display_name": PROJECT_DISPLAY_NAME}}),
            "--profile",
            PROFILE,
        ]
    )
    print(f"  Project {PROJECT_ID!r} created.")


def ensure_uc_catalog() -> None:
    if catalog_exists():
        print(f"  UC catalog {LAKEBASE_UC_CATALOG!r} already exists — skipping.")
        return
    print(f"  Registering Lakebase as UC catalog {LAKEBASE_UC_CATALOG!r} ...")
    run(
        [
            "databricks",
            "postgres",
            "create-catalog",
            LAKEBASE_UC_CATALOG,
            "--json",
            json.dumps(
                {
                    "spec": {
                        "postgres_database": POSTGRES_DATABASE,
                        "branch": BRANCH_PATH,
                    }
                }
            ),
            "--profile",
            PROFILE,
        ]
    )
    print(f"  UC catalog {LAKEBASE_UC_CATALOG!r} registered.")


def ensure_synced_tables(wait: bool) -> None:
    for table in SYNCED_TABLES:
        target = table["target"]
        if synced_table_exists(target):
            print(f"  Synced table {target!r} already exists — skipping create.")
            continue
        print(f"  Creating synced table {target!r} ...")
        spec = {
            "spec": {
                "source_table_full_name": table["source"],
                "primary_key_columns": table["primary_key_columns"],
                "scheduling_policy": "SNAPSHOT",
                "branch": BRANCH_PATH,
                "postgres_database": POSTGRES_DATABASE,
                "create_database_objects_if_missing": True,
                "new_pipeline_spec": {
                    "storage_catalog": STORAGE_CATALOG,
                    "storage_schema": STORAGE_SCHEMA,
                },
            }
        }
        cmd = [
            "databricks",
            "postgres",
            "create-synced-table",
            target,
            "--json",
            json.dumps(spec),
            "--profile",
            PROFILE,
            "--no-wait",
        ]
        run(cmd)
        print(f"  Synced table {target!r} submitted.")

    if wait:
        print("\n  Waiting for all synced tables to reach ONLINE state ...")
        _wait_for_online()


def _wait_for_online() -> None:
    start = time.time()
    while time.time() - start < MAX_WAIT_S:
        states = {t["target"]: synced_table_state(t["target"]) for t in SYNCED_TABLES}
        all_online = all(s == ONLINE_STATE for s in states.values())
        for target, state in states.items():
            print(f"    {target}: {state}")
        if all_online:
            print("  All synced tables are ONLINE.")
            return
        print(f"  Waiting {POLL_INTERVAL_S}s ...")
        time.sleep(POLL_INTERVAL_S)
    print(
        "  ERROR: Timed out waiting for synced tables to go ONLINE.",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    global PROFILE  # noqa: PLW0603
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile", default=PROFILE, help="Databricks CLI profile"
    )
    parser.add_argument(
        "--wait", action="store_true", help="Block until all synced tables are ONLINE"
    )
    args = parser.parse_args()
    PROFILE = args.profile

    print("=== Step 1: Ensure Lakebase project ===")
    ensure_project()

    print("\n=== Step 2: Ensure UC catalog registration ===")
    ensure_uc_catalog()

    print("\n=== Step 3: Create synced tables ===")
    ensure_synced_tables(wait=args.wait)

    print("\nDone. Run with --wait to block until all tables are ONLINE.")


if __name__ == "__main__":
    main()
