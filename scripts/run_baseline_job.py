# Databricks notebook source
# Runner notebook for the ICU readiness drift baseline + live-score snapshot.
# Deployed + executed as a one-off job by the controller (no manual step).
# Installs the model's flavor deps in-notebook (avoids the serverless
# environment-spec library-install conflict), then invokes the committed
# baseline module from the synced bundle files.

# COMMAND ----------
# MAGIC %pip install mlflow lightgbm shap
# COMMAND ----------
dbutils.library.restartPython()
# COMMAND ----------
import sys
sys.path.append("/Workspace/Users/matt.slack@databricks.com/.bundle/icu_step_down/sandbox/files")
import importlib
# Must equal the served version (resources/model_serving.yml entity_version);
# drift_check.py fails loudly on a baseline/served mismatch.
MODEL_VERSION = "6"
import src.monitoring.baseline as b
importlib.reload(b)

b.write_training_baseline(model_version=MODEL_VERSION)
b.append_live_snapshot(model_version=MODEL_VERSION)

spark.sql(
    "SELECT "
    "(SELECT COUNT(*) FROM icu_step_down.gold.readiness_training_baseline) AS baseline_rows, "
    "(SELECT COUNT(*) FROM icu_step_down.gold.readiness_score_history) AS history_rows"
).show()
print("BASELINE_JOB_OK")
