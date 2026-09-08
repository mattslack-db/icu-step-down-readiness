"""
ICU Step-Down Readiness pyfunc model.

Logged via mlflow.pyfunc.log_model(python_model="model.py") — the
"Models from Code" pattern (no pickling).  The serving runtime executes
this file verbatim; mlflow.models.set_model(ReadinessModel()) at the
bottom tells MLflow which class to instantiate.

Input  (per-request):  pandas DataFrame with FEATURE_COLS columns.
Output (per-request):  pandas DataFrame with one column "prediction"
                       containing a JSON string per row:
                         {
                           "readiness_score": float,   # P(safe step-down)
                           "factors": [
                             {"name": str,
                              "direction": "supports"|"risk",
                              "magnitude": float},
                             ...                        # top-5 by |SHAP|
                           ]
                         }
"""

import json

import mlflow
import numpy as np
import pandas as pd
from mlflow.pyfunc import PythonModel

# Ordered feature list — must match training order exactly.
# Keys (subject_id, hadm_id, icustay_id) are intentionally excluded.
FEATURE_COLS = [
    "hr_mean",
    "hr_min",
    "hr_max",
    "hr_last",
    "sbp_mean",
    "sbp_min",
    "sbp_max",
    "sbp_last",
    "dbp_mean",
    "dbp_min",
    "dbp_max",
    "dbp_last",
    "spo2_mean",
    "spo2_min",
    "spo2_max",
    "spo2_last",
    "temp_c_mean",
    "temp_c_min",
    "temp_c_max",
    "temp_c_last",
    "rr_mean",
    "rr_min",
    "rr_max",
    "rr_last",
    "on_vasopressors",
    "on_ventilator",
    "gcs_last",
    "lactate_last",
    "los",
    "age",
]

TOP_N_FACTORS = 5


class ReadinessModel(PythonModel):
    """
    Wraps a LightGBM Booster and a SHAP TreeExplainer.

    load_context:  loads lgbm_model artifact, initialises SHAP explainer.
    predict:       returns readiness_score + top-N factors per row.
    """

    def load_context(self, context):
        import lightgbm as lgb
        import shap

        self.lgbm = lgb.Booster(model_file=context.artifacts["lgbm_model"])
        # TreeExplainer is fast on tree models (no sampling).
        self.explainer = shap.TreeExplainer(self.lgbm)

    def predict(self, context, model_input: pd.DataFrame, params=None) -> pd.DataFrame:
        # --- coerce inputs ------------------------------------------------
        X = model_input[FEATURE_COLS].copy()
        # Cast everything to numeric; non-parseable → NaN (LightGBM handles NaN natively).
        for col in FEATURE_COLS:
            if X[col].dtype == object or str(X[col].dtype) == "boolean":
                X[col] = pd.to_numeric(X[col], errors="coerce")
            elif X[col].dtype == bool:
                X[col] = X[col].astype(float)
        X_arr = X.to_numpy(dtype=np.float64)

        # --- score --------------------------------------------------------
        # lgbm.predict() returns P(label=1) directly for binary classification.
        scores = self.lgbm.predict(X_arr)

        # --- SHAP ---------------------------------------------------------
        # TreeExplainer returns an array (n_samples, n_features) for binary
        # classification — SHAP values in log-odds space for label=1.
        # Positive SHAP → feature pushes toward safe step-down ("supports").
        # Negative SHAP → feature pushes toward bounce-back ("risk").
        raw_shap = self.explainer.shap_values(X_arr)
        # Handle both formats: ndarray or list-of-arrays (older shap versions).
        if isinstance(raw_shap, list):
            shap_arr = raw_shap[1]  # index-1 = positive-class values
        else:
            shap_arr = raw_shap  # already (n_samples, n_features)

        # --- build output -------------------------------------------------
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
            results.append(
                json.dumps(
                    {"readiness_score": float(scores[i]), "factors": factors}
                )
            )

        return pd.DataFrame({"prediction": results})


mlflow.models.set_model(ReadinessModel())
