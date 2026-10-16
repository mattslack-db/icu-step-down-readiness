"""Offline AUC experiments behind model v7 — nothing is registered or deployed.

Run pull_cohort_data.py first (read-only pull to ./data), then:
    uv run --with lightgbm --with scikit-learn --with pandas --with pyarrow \
        python scripts/ml_experiments/cohort_experiment.py
Results: evidence/ml-cohort-experiment.md
"""
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tests" / "ml"))
from test_feature_parity import MODEL_PY, _module_lists
FEATURES = _module_lists(MODEL_PY)["FEATURE_COLS"]

DATA = Path(__file__).parent / "data"
PARAMS = dict(n_estimators=2000, num_leaves=63, max_depth=6, learning_rate=0.05,
              min_child_samples=20, reg_alpha=0.1, reg_lambda=1.0,
              class_weight="balanced", random_state=42, n_jobs=-1, verbose=-1)


def load() -> tuple[pd.DataFrame, list[str]]:
    base = pd.read_parquet(DATA / "base.parquet")
    trends = pd.read_parquet(DATA / "trends.parquet").pivot(
        index="icustay_id", columns="vital_name", values=["delta_6h", "slope_24h", "n_last6h"])
    trends.columns = [f"{v}_{m}" for m, v in trends.columns]
    vent = pd.read_parquet(DATA / "vent.parquet").set_index("icustay_id")
    df = base.join(trends, on="icustay_id").join(vent, on="icustay_id")
    new_cols = ["discharge_hour", "discharge_weekend", "discharge_night", "hours_since_vent",
                *trends.columns]
    for c in FEATURES + new_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    df["icustay_num"] = pd.to_numeric(df["icustay_id"])
    return df.sort_values("icustay_num").reset_index(drop=True), new_cols


def split(df, by_patient=False):
    """64/16/20 split; stratified by label, or grouped by patient."""
    if by_patient:
        g = df["subject_id"]
        tv_idx, te_idx = next(GroupShuffleSplit(1, test_size=0.2, random_state=42).split(df, groups=g))
        tv = df.iloc[tv_idx]
        tr_idx, va_idx = next(GroupShuffleSplit(1, test_size=0.2, random_state=42).split(tv, groups=tv["subject_id"]))
        return tv.iloc[tr_idx], tv.iloc[va_idx], df.iloc[te_idx]
    tv, te = train_test_split(df, test_size=0.2, random_state=42, stratify=df["y"])
    tr, va = train_test_split(tv, test_size=0.2, random_state=42, stratify=tv["y"])
    return tr, va, te


def fit(tr, va, cols, params=PARAMS):
    m = LGBMClassifier(**params)
    m.fit(tr[cols], tr["y"], eval_set=[(va[cols], va["y"])], eval_metric="auc",
          callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(-1)])
    return m


def ci(y, p, n=1000):
    """95% percentile bootstrap — same method and seed as bootstrap_auc_ci in
    src/ml/train.py (a Databricks notebook, so not importable here). A fresh
    RNG per call keeps each run's CI independent of the runs before it."""
    rng = np.random.default_rng(0)
    y, p = np.asarray(y), np.asarray(p)
    point = roc_auc_score(y, p)
    stats = []
    for _ in range(n):
        i = rng.integers(0, len(y), len(y))
        if y[i].min() != y[i].max():
            stats.append(roc_auc_score(y[i], p[i]))
    lo, hi = np.percentile(stats, [2.5, 97.5])
    return f"{point:.3f} [{lo:.3f}-{hi:.3f}]"


def report(name, te, prob_notsafe):
    """prob_notsafe: higher = more likely NOT safe."""
    y_ns = (te["label_reason"] != "safe").astype(int)
    readmit = te["label_reason"].isin(["safe", "bounce_back"])
    print(f"{name:<58} AUC {ci(y_ns, prob_notsafe)} | "
          f"readmit-only {ci(y_ns[readmit], prob_notsafe[readmit])} | "
          f"PR-AUC {average_precision_score(y_ns, prob_notsafe):.3f} (base {y_ns.mean():.3f}) | n_pos {y_ns.sum()}")


def run(df, cols, name, target="notsafe", by_patient=False, params=PARAMS):
    """Split the cohort ONCE on the not-safe label; for target='bounce' train only on
    the safe/bounce-back rows of TRAIN/VAL, but always evaluate on the full TEST."""
    d = df.copy()
    d["y"] = (d["label_reason"] != "safe").astype(int)
    tr, va, te = split(d, by_patient)
    if target == "bounce":
        keep = lambda x: x[x["label_reason"].isin(["safe", "bounce_back"])]
        tr, va = keep(tr), keep(va)
    m = fit(tr, va, cols, params)
    report(name, te, pd.Series(m.predict_proba(te[cols])[:, 1], index=te.index))
    return m


if __name__ == "__main__":
    df, NEW = load()
    print(f"rows {len(df):,}; died_in_icu {int(df.died_in_icu.sum()):,}; new features {len(NEW)}\n")
    alive = df[(df.died_in_icu == 0) & (df.label_reason != "still_in_icu")]
    print(f"honest cohort (left ICU alive): {len(alive):,}; label_reason:\n{alive.label_reason.value_counts().to_string()}\n")

    run(df, FEATURES, "A  v6 as-is (all stays, 53 feats)")
    run(alive, FEATURES, "B  left ICU alive, 53 feats")
    run(alive, FEATURES, "B' left ICU alive, 53 feats, patient-grouped split", by_patient=True)
    run(alive, FEATURES + NEW, "C  B + discharge context + trends + time-off-vent")
    run(alive, FEATURES + NEW, "C' C, patient-grouped split", by_patient=True)
    run(alive, FEATURES + NEW, "D  C, trained on bounce-back vs safe only", target="bounce")
    tuned = {**PARAMS, "num_leaves": 15, "min_child_samples": 100, "learning_rate": 0.03, "max_depth": -1}
    run(alive, FEATURES + NEW, "D' D tuned (leaves=15 min_child=100)", target="bounce", params=tuned)
    run(alive, FEATURES, "D'' bounce-only target, 53 feats only, tuned", target="bounce", params=tuned)
    for nl, mcs, lr in [(15, 100, 0.03), (31, 50, 0.03), (7, 200, 0.02)]:
        p = {**PARAMS, "num_leaves": nl, "min_child_samples": mcs, "learning_rate": lr, "max_depth": -1}
        run(alive, FEATURES + NEW, f"E  C tuned leaves={nl} min_child={mcs} lr={lr}", params=p)
