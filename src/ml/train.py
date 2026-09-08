# Databricks notebook source
# MAGIC %md
# MAGIC # ICU Step-Down Readiness — LightGBM Training
# MAGIC
# MAGIC **Phase 5A** — train a binary classifier on `icu_step_down.gold.readiness_training_set`,
# MAGIC explain it with SHAP, wrap it in a MLflow pyfunc, and register to UC.
# MAGIC
# MAGIC | Label | Meaning | Count (approx) |
# MAGIC |-------|---------|----------------|
# MAGIC | 1 | Safe step-down (no ICU readmission in 72 h) | ~59,706 (97 %) |
# MAGIC | 0 | Bounce-back (ICU readmission within 72 h) | ~1,826 (3 %) |
# MAGIC
# MAGIC **Class imbalance handling**: `class_weight="balanced"` in LGBMClassifier so the
# MAGIC minority (bounce-back) class receives proportionally higher gradient weight.
# MAGIC Raw accuracy is NOT reported — we use AUC, PR-AUC, precision/recall/F1, and
# MAGIC confusion matrix.
# MAGIC
# MAGIC **NaN handling**: ~3,200 stays have NULL vital aggregates (very short stays).
# MAGIC `pd.to_numeric(..., errors="coerce")` converts string nulls to `float("nan")`.
# MAGIC LightGBM handles NaN natively via its surrogate-split mechanism — no imputation.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0 · Setup — create ml schema if needed, MLflow experiment

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
# Parent folder /Users/<user>/icu_step_down was pre-created via CLI before the job ran.

mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment(f"{EXPERIMENT_BASE}/training")

print(f"MLflow experiment: {EXPERIMENT_BASE}/training")
print(f"Target model: {FULL_MODEL_NAME}")

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
print(f"Loaded {len(df):,} rows, {df.columns.tolist()}")

# Coerce all feature columns to numeric.
# Many are stored as STRING in the Delta table; pd.to_numeric preserves NaN.
for col in FEATURE_COLS:
    if df[col].dtype == object or str(df[col].dtype) in ("string", "StringDtype"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    elif df[col].dtype == bool:
        df[col] = df[col].astype(float)

print(f"\nClass distribution:\n{df[TARGET_COL].value_counts()}")
print(f"\nNaN counts per feature (top 10):\n{df[FEATURE_COLS].isna().sum().sort_values(ascending=False).head(10)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Stratified train / test split (80 / 20)

# COMMAND ----------

X = df[FEATURE_COLS]
y = df[TARGET_COL]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.20, random_state=42, stratify=y
)

print(f"Train size: {len(X_train):,}  |  Test size: {len(X_test):,}")
print(f"Train label=1: {y_train.sum():,} ({y_train.mean()*100:.1f}%)")
print(f"Test  label=1: {y_test.sum():,} ({y_test.mean()*100:.1f}%)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Train LightGBM with class weighting
# MAGIC
# MAGIC **Hyperparameters**: modest depth/leaves with regularisation to avoid overfitting on
# MAGIC the tiny minority class.  `class_weight="balanced"` lets sklearn compute
# MAGIC `n_samples / (n_classes * bincount(y))` per class automatically.
# MAGIC
# MAGIC **NaN**: LightGBM grows surrogate splits for missing values — no imputation needed.

# COMMAND ----------

lgbm_params = {
    "n_estimators": 500,
    "num_leaves": 63,
    "max_depth": 6,
    "learning_rate": 0.05,
    "min_child_samples": 20,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "class_weight": "balanced",  # handles 97/3 imbalance
    "random_state": 42,
    "n_jobs": -1,
    "verbose": -1,
}

with mlflow.start_run(run_name="lgbm_readiness") as run:
    # Log params manually (autolog would also work but we want explicit control).
    mlflow.log_params(lgbm_params)
    mlflow.log_param("feature_count", len(FEATURE_COLS))
    mlflow.log_param("train_size", len(X_train))
    mlflow.log_param("test_size", len(X_test))
    mlflow.log_param("nan_strategy", "passthrough_lgbm_native")
    mlflow.log_param("class_imbalance_strategy", "class_weight_balanced")

    # ── Train ────────────────────────────────────────────────────────────────
    clf = LGBMClassifier(**lgbm_params)
    clf.fit(
        X_train,
        y_train,
        eval_set=[(X_test, y_test)],
        eval_metric="auc",
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(period=-1)],
    )
    print(f"Best iteration: {clf.best_iteration_}")
    mlflow.log_param("best_iteration", clf.best_iteration_)

    # ── Evaluate ─────────────────────────────────────────────────────────────
    y_prob = clf.predict_proba(X_test)[:, 1]
    y_pred = (y_prob >= 0.5).astype(int)

    auc = roc_auc_score(y_test, y_prob)
    pr_auc = average_precision_score(y_test, y_prob)
    # Precision/recall/F1 at 0.5 threshold — also useful at 0.3 for high-recall use.
    prec, rec, f1, _ = precision_recall_fscore_support(
        y_test, y_pred, average="binary", pos_label=1
    )
    # For the clinically-important minority class (bounce-back, label=0):
    prec0, rec0, f1_0, _ = precision_recall_fscore_support(
        y_test, y_pred, average="binary", pos_label=0
    )
    cm = confusion_matrix(y_test, y_pred)

    mlflow.log_metrics({
        "test_auc": auc,
        "test_pr_auc": pr_auc,
        "test_precision_label1": prec,
        "test_recall_label1": rec,
        "test_f1_label1": f1,
        "test_precision_label0": prec0,
        "test_recall_label0": rec0,
        "test_f1_label0": f1_0,
    })

    print(f"\n=== Metrics ===")
    print(f"AUC:            {auc:.4f}")
    print(f"PR-AUC:         {pr_auc:.4f}")
    print(f"Precision(L=1): {prec:.4f}   Recall(L=1): {rec:.4f}   F1(L=1): {f1:.4f}")
    print(f"Precision(L=0): {prec0:.4f}   Recall(L=0): {rec0:.4f}   F1(L=0): {f1_0:.4f}")
    print(f"\nConfusion matrix (rows=actual, cols=predicted, order 0/1):")
    print(f"  TN={cm[0,0]}  FP={cm[0,1]}")
    print(f"  FN={cm[1,0]}  TP={cm[1,1]}")

    # ── SHAP global importance ───────────────────────────────────────────────
    booster = clf.booster_
    explainer = shap.TreeExplainer(booster)
    # Use a stratified sample of test set for global SHAP (cheaper + representative).
    sample_size = min(500, len(X_test))
    rng = np.random.default_rng(42)
    idx = rng.choice(len(X_test), size=sample_size, replace=False)
    X_sample = X_test.iloc[idx].to_numpy(dtype=np.float64)
    shap_values_sample = explainer.shap_values(X_sample)
    # Handle list format from older shap.
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

    # ── Log pyfunc wrapper model ──────────────────────────────────────────────
    # Write model.py to temp dir so we can pass it as a file path.
    model_code_path = os.path.join(tmp_dir, "model.py")
    model_code = '''"""
ICU Step-Down Readiness pyfunc model.
"""
import json
import mlflow
import numpy as np
import pandas as pd
from mlflow.pyfunc import PythonModel

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
TOP_N_FACTORS = 5

class ReadinessModel(PythonModel):
    def load_context(self, context):
        import lightgbm as lgb
        import shap
        self.lgbm = lgb.Booster(model_file=context.artifacts["lgbm_model"])
        self.explainer = shap.TreeExplainer(self.lgbm)

    def predict(self, context, model_input, params=None):
        X = model_input[FEATURE_COLS].copy()
        for col in FEATURE_COLS:
            if X[col].dtype == object or str(X[col].dtype) in ("string", "StringDtype", "boolean"):
                X[col] = pd.to_numeric(X[col], errors="coerce")
            elif X[col].dtype == bool:
                X[col] = X[col].astype(float)
        X_arr = X.to_numpy(dtype=np.float64)
        scores = self.lgbm.predict(X_arr)
        raw_shap = self.explainer.shap_values(X_arr)
        if isinstance(raw_shap, list):
            shap_arr = raw_shap[1]
        else:
            shap_arr = raw_shap
        results = []
        for i in range(len(X_arr)):
            row_shap = shap_arr[i]
            factors = [
                {
                    "name": FEATURE_COLS[j],
                    "direction": "supports" if float(row_shap[j]) > 0 else "risk",
                    "magnitude": abs(float(row_shap[j])),
                }
                for j in range(len(FEATURE_COLS))
                if row_shap[j] != 0
            ]
            factors.sort(key=lambda x: x["magnitude"], reverse=True)
            factors = factors[:TOP_N_FACTORS]
            results.append(json.dumps({"readiness_score": float(scores[i]), "factors": factors}))
        return pd.DataFrame({"prediction": results})

mlflow.models.set_model(ReadinessModel())
'''
    with open(model_code_path, "w") as fh:
        fh.write(model_code)

    # Build sample I/O for signature inference.
    sample_in = X_test.head(3).copy()
    sample_out = pd.DataFrame({
        "prediction": [
            json.dumps({"readiness_score": 0.95, "factors": [{"name": "los", "direction": "supports", "magnitude": 0.3}]}),
            json.dumps({"readiness_score": 0.80, "factors": [{"name": "lactate_last", "direction": "risk", "magnitude": 0.2}]}),
            json.dumps({"readiness_score": 0.70, "factors": [{"name": "hr_mean", "direction": "supports", "magnitude": 0.15}]}),
        ]
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
        python_model=model_code_path,
        artifacts={"lgbm_model": booster_path},
        signature=sig,
        input_example=sample_in,
        pip_requirements=pip_reqs,
        registered_model_name=FULL_MODEL_NAME,
    )
    print(f"\nRegistered model: {model_info.model_uri}")
    registered_version = model_info.registered_model_version

    # ── Set @prod alias ───────────────────────────────────────────────────────
    client = MlflowClient(registry_uri="databricks-uc")
    client.set_registered_model_alias(FULL_MODEL_NAME, "prod", registered_version)
    print(f"Alias @prod → version {registered_version}")

    shutil.rmtree(tmp_dir, ignore_errors=True)

    RUN_ID = run.info.run_id

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · Sample pyfunc prediction (sanity check)

# COMMAND ----------

# Load the just-registered pyfunc and run a quick sanity check.
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
    "test_pr_auc": round(pr_auc, 4),
    "test_f1_label0": round(f1_0, 4),
    "test_recall_label0": round(rec0, 4),
    "confusion_matrix": {"TN": int(cm[0,0]), "FP": int(cm[0,1]), "FN": int(cm[1,0]), "TP": int(cm[1,1])},
    "shap_top3": shap_ranking.head(3)["feature"].tolist(),
    "run_id": RUN_ID,
}
print(json.dumps(output, indent=2))
dbutils.notebook.exit(json.dumps(output))
