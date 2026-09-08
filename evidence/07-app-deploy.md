# Phase 7B — App Deploy Evidence

## App URL

```
https://icu-step-down-7474646035095173.aws.databricksapps.com
```

## Deploy Log (final successful deployment)

Deployed via DABs on 2026-09-08:

```
databricks bundle deploy -t sandbox --profile icu-sandbox
# → Deployment complete!

databricks bundle run icu-step-down-app -t sandbox --profile icu-sandbox
# → App started successfully
# → https://icu-step-down-7474646035095173.aws.databricksapps.com
```

App status confirmed RUNNING at 2026-09-08T13:29:xx UTC.
Startup log: `2026-09-08T13:29:xx [APP] INFO: Application startup complete.`

## Post-Deploy Grant Statements

### 1. Lakebase role for app SP (LAKEBASE_OAUTH_V1 auth)

The app SP `a42853b7-d35c-444e-81a1-023b2178d8fb` needed a Lakebase-managed
role with `auth_method=LAKEBASE_OAUTH_V1` to authenticate via OAuth tokens.
A manually-created Postgres role has `NO_LOGIN` in Lakebase's view and is
rejected. The correct approach uses the Lakebase SDK:

```python
from databricks.sdk.service.postgres import (
    Role, RoleAttributes, RoleAuthMethod, RoleIdentityType, RoleRoleSpec
)

spec = RoleRoleSpec(
    auth_method=RoleAuthMethod.LAKEBASE_OAUTH_V1,
    identity_type=RoleIdentityType.SERVICE_PRINCIPAL,
    postgres_role="a42853b7-d35c-444e-81a1-023b2178d8fb",
    attributes=RoleAttributes(bypassrls=False, createdb=False, createrole=False),
)
new_role = Role(spec=spec)
ws.postgres.create_role(
    parent="projects/icu-step-down/branches/production",
    role=new_role,
    role_id="app-sp",
)
# → Lakebase role created: auth_method=LAKEBASE_OAUTH_V1 pg_role=a42853b7-d35c-444e-81a1-023b2178d8fb
```

### 2. Postgres-level schema grants

```sql
GRANT USAGE ON SCHEMA mimic_iii TO "a42853b7-d35c-444e-81a1-023b2178d8fb";
GRANT SELECT ON ALL TABLES IN SCHEMA mimic_iii TO "a42853b7-d35c-444e-81a1-023b2178d8fb";
ALTER DEFAULT PRIVILEGES IN SCHEMA mimic_iii
  GRANT SELECT ON TABLES TO "a42853b7-d35c-444e-81a1-023b2178d8fb";
```

Verified:
```
Tables with SELECT: census, census_vitals, patient_features
```

### 3. Workspace-level permission on database-projects

```python
ws.permissions.update(
    request_object_type="database-projects",
    request_object_id="icu-step-down",
    access_control_list=[
        AccessControlRequest(
            service_principal_name="a42853b7-d35c-444e-81a1-023b2178d8fb",
            permission_level=PermissionLevel.CAN_USE,
        )
    ],
)
```

### 4. Serving endpoint: CAN_QUERY

Granted via DABs `databricks.yml` resources block:
```yaml
resources:
  - name: "icu-readiness"
    serving_endpoint:
      name: "icu-readiness"
      permission: "CAN_QUERY"
```

## Real API Responses from Deployed App

### GET /api/version

```bash
curl -H "Authorization: Bearer <token>" \
  https://icu-step-down-7474646035095173.aws.databricksapps.com/api/version
```
```json
{"version":"0.0.0+20260908132954"}
```

### GET /api/analytics (aggregate — no raw patient rows)

```bash
curl -H "Authorization: Bearer <token>" \
  https://icu-step-down-7474646035095173.aws.databricksapps.com/api/analytics
```
```json
{
  "total_census": 40,
  "band_distribution": [
    {"band": "Ready", "count": 13, "pct": 32.5},
    {"band": "Borderline", "count": 13, "pct": 32.5},
    {"band": "Not ready", "count": 14, "pct": 35.0}
  ],
  "feature_importance": [
    {"feature": "last lactate", "importance": 0.2458},
    {"feature": "age (years)", "importance": 0.0462},
    {"feature": "ICU length of stay (days)", "importance": 0.03491},
    {"feature": "GCS (last)", "importance": 0.02956},
    {"feature": "last SpO₂", "importance": 0.02939}
  ],
  "avg_los_by_band": {"Not ready": 3.39, "Ready": 2.71, "Borderline": 2.34},
  "vent_rate": 0.275,
  "vasopressor_rate": 0.2,
  "generated_at": "2026-09-08T13:30:34.685002+00:00"
}
```

### GET /api/census (summary — first patient only, no bulk rows)

```bash
curl -H "Authorization: Bearer <token>" \
  https://icu-step-down-7474646035095173.aws.databricksapps.com/api/census
```
```json
{
  "total": 40,
  "generated_at": "2026-09-08T13:30:35.426732+00:00",
  "first_patient_summary": {
    "icustay_id": "287070",
    "readiness_index": 98,
    "band": "Ready",
    "age": 74.6,
    "los": 1.08
  }
}
```
(Full response has 40 patients; only first patient summary shown here to avoid bulk rows.)

## Verification Method

1. `databricks apps get icu-step-down --profile icu-sandbox` → `state: RUNNING`
2. Browser screenshots: `evidence/screenshot-census.png`, `screenshot-patient-detail.png`,
   `screenshot-analytics.png` (local dev server, same data)
3. Three curl calls above confirmed text response from deployed URL

## App Service Principal

| Field | Value |
|---|---|
| SP client_id | `a42853b7-d35c-444e-81a1-023b2178d8fb` |
| SP numeric ID | `79018491879389` |
| SP display name | `app-5wvxyo icu-step-down` |
| Lakebase role | `projects/icu-step-down/branches/production/roles/app-sp` |
| Lakebase auth | `LAKEBASE_OAUTH_V1` |
