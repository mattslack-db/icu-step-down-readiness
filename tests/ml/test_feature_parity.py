"""Feature-list parity across training, the served pyfunc, and the app.

The model is scored with columns the app selects from Lakebase, so the three
FEATURE_COLS definitions must be identical and in the same order — a drift
here silently misaligns features at serving time.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

TRAIN_PY = ROOT / "src" / "ml" / "train.py"
MODEL_PY = ROOT / "src" / "ml" / "model.py"
APP_CENSUS_PY = ROOT / "app" / "src" / "icu_step_down" / "backend" / "routers" / "census.py"
DRIFT_BASELINE_PY = ROOT / "src" / "monitoring" / "baseline.py"
GOLD_SQL = ROOT / "src" / "pipelines" / "gold.sql"

V3_NEW_FEATURES = {
    "hr_std", "sbp_std", "rr_std", "spo2_std", "n_vital_obs",
    "creatinine_last", "bun_last", "wbc_last", "hemoglobin_last",
    "platelets_last", "bicarbonate_last", "sodium_last", "potassium_last",
    "glucose_last", "urine_output_24h", "vasopressors_24h", "ventilated_24h",
    "prior_icu_stays", "is_emergency_admit", "hours_admit_to_icu",
    "is_surgical_unit", "is_cardiac_unit", "is_male",
}


def _module_lists(path: Path) -> dict[str, list[str]]:
    """Return every module-level NAME = [..str..] (or NAME = A + [..]) assignment."""
    tree = ast.parse(path.read_text())
    lists: dict[str, list[str]] = {}

    def resolve(node: ast.AST) -> list[str] | None:
        if isinstance(node, ast.List):
            return [elt.value for elt in node.elts if isinstance(elt, ast.Constant)]
        if isinstance(node, ast.Name) and node.id in lists:
            return lists[node.id]
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left, right = resolve(node.left), resolve(node.right)
            if left is not None and right is not None:
                return left + right
        return None

    for stmt in tree.body:
        targets = stmt.targets if isinstance(stmt, ast.Assign) else (
            [stmt.target] if isinstance(stmt, ast.AnnAssign) and stmt.value else []
        )
        value = stmt.value if isinstance(stmt, (ast.Assign, ast.AnnAssign)) else None
        for target in targets:
            if isinstance(target, ast.Name) and value is not None:
                resolved = resolve(value)
                if resolved is not None:
                    lists[target.id] = resolved
    return lists


def test_train_and_model_feature_lists_match():
    assert _module_lists(TRAIN_PY)["FEATURE_COLS"] == _module_lists(MODEL_PY)["FEATURE_COLS"]


def test_app_scores_with_the_model_feature_list():
    assert _module_lists(APP_CENSUS_PY)["FEATURE_COLS"] == _module_lists(MODEL_PY)["FEATURE_COLS"]


def test_drift_baseline_scores_with_the_model_feature_list():
    assert _module_lists(DRIFT_BASELINE_PY)["_FEATURE_COLS"] == _module_lists(MODEL_PY)["FEATURE_COLS"]


def test_pipeline_ai_query_scores_with_the_model_feature_list():
    """gold.census_scores builds the ai_query request from an explicit column list."""
    import re

    sql = GOLD_SQL.read_text()
    block = sql[sql.index("CREATE OR REFRESH MATERIALIZED VIEW icu_step_down.gold.census_scores"):]
    block = block[block.index("named_struct("):block.index("returnType")]
    cols = re.findall(r"'(\w+)', CAST\(\1 AS DOUBLE\)", block)
    assert cols == _module_lists(MODEL_PY)["FEATURE_COLS"]


def test_model_includes_v3_features_without_duplicates():
    cols = _module_lists(MODEL_PY)["FEATURE_COLS"]
    assert V3_NEW_FEATURES <= set(cols)
    assert len(cols) == len(set(cols))


def test_identifiers_are_never_features():
    cols = set(_module_lists(MODEL_PY)["FEATURE_COLS"])
    assert not cols & {"subject_id", "hadm_id", "icustay_id", "dob", "care_unit", "label_reason"}
