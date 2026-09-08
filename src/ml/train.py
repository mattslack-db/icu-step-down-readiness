# Databricks notebook source
# MAGIC %md
# MAGIC # ICU Step-Down Readiness — LightGBM Training
# MAGIC
# MAGIC **Phase 5A (v2 — clean eval)** — train a binary classifier on
# MAGIC `icu_step_down.gold.readiness_training_set`, explain it with SHAP, wrap it in a
# MAGIC MLflow pyfunc, and register to UC.
# MAGIC
# MAGIC | Label | Meaning | Count (approx) |
# MAGIC |-------|---------|----------------|
# MAGIC | 1 | Safe step-down (no ICU readmission in 72 h) | ~59,706 (97 %) |
# MAGIC | 0 | Bounce-back (ICU readmission within 72 h) | ~1,826 (3 %) |
# MAGIC
# MAGIC **Class imbalance**: `class_weight="balanced"` — minority bounce-back class
# MAGIC receives proportionally higher gradient weight.
# MAGIC
# MAGIC **NaN handling**: ~3,200 stays have NULL vital aggregates (very short stays).
# MAGIC `pd.to_numeric(..., errors="coerce")` converts string nulls to `float("nan")`.
# MAGIC LightGBM handles NaN natively via surrogate splits — no imputation.
# MAGIC
# MAGIC **Split**: three-way stratified (64 % train / 16 % val / 20 % test).
# MAGIC Early stopping uses VAL only; TEST set is untouched until final evaluation.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0 · Setup

# COMMAND ----------

import json
import os
import shutil
import tempfile

import lightgbm as lgb
import mlflow
import mlflow.lightgbm
import mlflow.pyfunc
import numpy as np
import pandas as pd
import shap
from lightgbm import LGBMClassifier
from mlflow.models import infer_signature
from mlflow.tracking import MlflowClient
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

# Create ml schema if it doesn't exist.
spark.sql("CREATE SCHEMA IF NOT EXISTS icu_step_down.ml")

CATALOG = "icu_step_down"
SCHEMA = "ml"
MODEL_NAME = "readiness_model"
FULL_MODEL_NAME = f"{CATALOG}.{SCHEMA}.{MODEL_NAME}"
ENDPOINT_NAME = "icu-readiness"

USER_EMAIL = spark.sql("SELECT current_user()").collect()[0][0]
EXPERIMENT_BASE = f"/Users/{USER_EMAIL}/icu_step_down"
# model.py is uploaded alongside this notebook — access via the /Workspace/ mount.
MODEL_PY_PATH = f"/Workspace/Users/{USER_EMAIL}/icu_step_down/model.py"

print(f"MLflow experiment : {EXPERIMENT_BASE}/training")
print(f"Target model      : {FULL_MODEL_NAME}")
print(f"pyfunc model.py   : {MODEL_PY_PATH}")
print(f"model.py exists   : {os.path.exists(MODEL_PY_PATH)}")

mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment(f"{EXPERIMENT_BASE}/training")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Load training data

# COMMAND ----------

FEATURE_COLS = [
    "hr_mean", "hr_min", "hr_max", "hr_last",
    "sbp_mean", "sbp_min", "sbp_max", "sbp_last",
    "dbp_mean", "dbp_min", "dbp_max", "dbp_last",
    "spo2_mean", "spo2_min", "spo2_max", "spo2_last",
    "temp_c_mean", "temp_c_min", "temp_c_max", "temp_c_last",
    "rr_mean", "rr_min", "rr_max", "rr_last",
    "on_vasopressors", "on_ventilator",
    "gcs_last", "lactate_last", "los", "age",
]
TARGET_COL = "readiness_label"
KEY_COLS = ["subject_id", "hadm_id", "icustay_id"]  # never used as features

df = spark.table(f"{CATALOG}.gold.readiness_training_set").toPandas()
print(f"Loaded {len(df):,} rows")

# Coerce all feature columns to numeric.
# Many are stored as STRING in the Delta table; pd.to_numeric preserves NaN.
for col in FEATURE_COLS:
    dtype_str = str(df[col].dtype)
    if dtype_str in ("object", "string", "StringDtype", "boolean"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    elif df[col].dtype == bool:
        df[col] = df[col].astype(float)

print(f"\nClass distribution:\n{df[TARGET_COL].value_counts()}")
print(f"\nNaN counts per feature (top 10):\n"
      f"{df[FEATURE_COLS].isna().sum().sort_values(ascending=False).head(10)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Three-way stratified split (64 / 16 / 20)
# MAGIC
# MAGIC VAL is used for early stopping only; TEST is touched exactly once for final metrics.

# COMMAND ----------

X = df[FEATURE_COLS]
y = df[TARGET_COL]

# Step 1: carve off 20 % test set (untouched until final evaluation).
X_trainval, X_test, y_trainval, y_test = train_test_split(
    X, y, test_size=0.20, random_state=42, stratify=y
)
# Step 2: split remainder 80/20 → train 64 % / val 16 % of total.
X_train, X_val, y_train, y_val = train_test_split(
    X_trainval, y_trainval, test_size=0.20, random_state=42, stratify=y_trainval
)

print(f"Train : {len(X_train):,} rows | label=1: {y_train.mean()*100:.1f}%")
print(f"Val   : {len(X_val):,} rows  | label=1: {y_val.mean()*100:.1f}%")
print(f"Test  : {len(X_test):,} rows  | label=1: {y_test.mean()*100:.1f}%")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Train LightGBM
# MAGIC
# MAGIC Early stopping uses **VAL**; final metrics are computed **once** on **TEST**.

# COMMAND ----------

lgbm_params = {
    "n_estimators": 500,
    "num_leaves": 63,
    "max_depth": 6,
    "learning_rate": 0.05,
    "min_child_samples": 20,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "class_weight": "balanced",   # handles 97/3 imbalance
    "random_state": 42,
    "n_jobs": -1,
    "verbose": -1,
}

with mlflow.start_run(run_name="lgbm_readiness_v2") as run:
    mlflow.log_params(lgbm_params)
    mlflow.log_param("feature_count", len(FEATURE_COLS))
    mlflow.log_param("train_size", len(X_train))
    mlflow.log_param("val_size", len(X_val))
    mlflow.log_param("test_size", len(X_test))
    mlflow.log_param("split_strategy", "3way_64_16_20_stratified")
    mlflow.log_param("nan_strategy", "passthrough_lgbm_native")
    mlflow.log_param("class_imbalance_strategy", "class_weight_balanced")

    # ── Train (early stopping on VAL) ────────────────────────────────────────
    clf = LGBMClassifier(**lgbm_params)
    clf.fit(
        X_train,
        y_train,
        eval_set=[(X_val, y_val)],   # VAL only — test set not touched here
        eval_metric="auc",
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(period=-1)],
    )
    print(f"Best iteration: {clf.best_iteration_}")
    mlflow.log_param("best_iteration", clf.best_iteration_)

    # ── Evaluate ONCE on the untouched TEST set ───────────────────────────────
    y_prob = clf.predict_proba(X_test)[:, 1]
    y_pred = (y_prob >= 0.5).astype(int)

    auc = roc_auc_score(y_test, y_prob)
    pr_auc_label1 = average_precision_score(y_test, y_prob)
    pr_auc_label0 = average_precision_score(y_test, 1 - y_prob, pos_label=0)  # bounce-back minority
    prec1, rec1, f1_1, _ = precision_recall_fscore_support(
        y_test, y_pred, average="binary", pos_label=1
    )
    prec0, rec0, f1_0, _ = precision_recall_fscore_support(
        y_test, y_pred, average="binary", pos_label=0
    )
    cm = confusion_matrix(y_test, y_pred)

    mlflow.log_metrics({
        "test_auc": auc,
        "test_pr_auc_label1": pr_auc_label1,
        "test_pr_auc_label0": pr_auc_label0,
        "test_precision_label1": prec1,
        "test_recall_label1": rec1,
        "test_f1_label1": f1_1,
        "test_precision_label0": prec0,
        "test_recall_label0": rec0,
        "test_f1_label0": f1_0,
    })

    print(f"\n=== Metrics (clean held-out test set) ===")
    print(f"AUC:                  {auc:.4f}")
    print(f"PR-AUC (label=1):     {pr_auc_label1:.4f}  (majority safe class — see note)")
    print(f"PR-AUC (label=0):     {pr_auc_label0:.4f}  (bounce-back detection — clinically meaningful)")
    print(f"Precision(L=1): {prec1:.4f}   Recall(L=1): {rec1:.4f}   F1(L=1): {f1_1:.4f}")
    print(f"Precision(L=0): {prec0:.4f}   Recall(L=0): {rec0:.4f}   F1(L=0): {f1_0:.4f}")
    print(f"\nConfusion matrix (rows=actual, cols=predicted, order 0/1):")
    print(f"  TN={cm[0,0]}  FP={cm[0,1]}")
    print(f"  FN={cm[1,0]}  TP={cm[1,1]}")

    # ── SHAP global importance ───────────────────────────────────────────────
    booster = clf.booster_
    explainer = shap.TreeExplainer(booster)
    sample_size = min(500, len(X_test))
    rng = np.random.default_rng(42)
    idx = rng.choice(len(X_test), size=sample_size, replace=False)
    X_sample = X_test.iloc[idx].to_numpy(dtype=np.float64)
    shap_values_sample = explainer.shap_values(X_sample)
    if isinstance(shap_values_sample, list):
        shap_arr = shap_values_sample[1]
    else:
        shap_arr = shap_values_sample

    mean_abs_shap = np.abs(shap_arr).mean(axis=0)
    shap_ranking = (
        pd.DataFrame({"feature": FEATURE_COLS, "mean_abs_shap": mean_abs_shap})
        .sort_values("mean_abs_shap", ascending=False)
        .reset_index(drop=True)
    )
    print(f"\n=== SHAP Global Importance (top 10) ===")
    print(shap_ranking.head(10).to_string(index=False))
    mlflow.log_text(shap_ranking.to_csv(index=False), "shap_global_importance.csv")

    # ── Save booster artifact ─────────────────────────────────────────────────
    tmp_dir = tempfile.mkdtemp()
    booster_path = os.path.join(tmp_dir, "readiness_lgbm.json")
    booster.save_model(booster_path)
    mlflow.log_artifact(booster_path, artifact_path="booster")

    # ── Log pyfunc via src/ml/model.py (single source of truth) ─────────────
    # MODEL_PY_PATH is the workspace path where src/ml/model.py was uploaded.
    # Logging it here means committed == deployed — the same file is used.
    assert os.path.exists(MODEL_PY_PATH), (
        f"model.py not found at {MODEL_PY_PATH}. "
        "Upload src/ml/model.py to the workspace before running this notebook."
    )

    sample_in = X_test.head(3).copy()
    sample_out = pd.DataFrame({
        "prediction": [
            json.dumps({"readiness_score": 0.95,
                        "factors": [{"name": "los", "direction": "supports", "magnitude": 0.3}]}),
        ] * 3
    })
    sig = infer_signature(sample_in, sample_out)

    pip_reqs = [
        "mlflow",
        "lightgbm>=4.0.0",
        "shap>=0.45.0",
        "scikit-learn>=1.3.0",
        "pandas>=2.0.0",
        "numpy>=1.24.0",
    ]

    model_info = mlflow.pyfunc.log_model(
        artifact_path="model",
        python_model=MODEL_PY_PATH,          # committed src/ml/model.py
        artifacts={"lgbm_model": booster_path},
        signature=sig,
        input_example=sample_in,
        pip_requirements=pip_reqs,
        registered_model_name=FULL_MODEL_NAME,
    )
    print(f"\nRegistered model: {model_info.model_uri}")
    registered_version = model_info.registered_model_version

    client = MlflowClient(registry_uri="databricks-uc")
    client.set_registered_model_alias(FULL_MODEL_NAME, "prod", registered_version)
    print(f"Alias @prod → version {registered_version}")

    shutil.rmtree(tmp_dir, ignore_errors=True)
    RUN_ID = run.info.run_id

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · Sample pyfunc prediction (sanity check)

# COMMAND ----------

model_uri = f"models:/{FULL_MODEL_NAME}@prod"
pyfunc_model = mlflow.pyfunc.load_model(model_uri)
sample_rows = X_test.head(3)
pyfunc_out = pyfunc_model.predict(sample_rows)
print("Sample pyfunc output:")
for i, row in pyfunc_out.iterrows():
    parsed = json.loads(row["prediction"])
    print(f"\nRow {i}: score={parsed['readiness_score']:.4f}")
    for f in parsed["factors"]:
        print(f"  {f['direction']:8s} | {f['name']:20s} | {f['magnitude']:.4f}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5 · Summary output

# COMMAND ----------

output = {
    "model_version": str(registered_version),
    "model_uri": model_uri,
    "test_auc": round(auc, 4),
    "test_pr_auc_label1": round(pr_auc_label1, 4),
    "test_pr_auc_label0": round(pr_auc_label0, 4),
    "test_f1_label0": round(f1_0, 4),
    "test_recall_label0": round(rec0, 4),
    "test_precision_label0": round(prec0, 4),
    "confusion_matrix": {
        "TN": int(cm[0, 0]),
        "FP": int(cm[0, 1]),
        "FN": int(cm[1, 0]),
        "TP": int(cm[1, 1]),
    },
    "shap_top3": shap_ranking.head(3)["feature"].tolist(),
    "run_id": RUN_ID,
    "model_py_path": MODEL_PY_PATH,
}
print(json.dumps(output, indent=2))
dbutils.notebook.exit(json.dumps(output))
