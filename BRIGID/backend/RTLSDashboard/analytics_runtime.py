"""
analytics_runtime.py
====================

Transforms RTLS CSV logs into model-ready exposure windows for the RTLS
Dashboard analytics tab. The bundled model is evaluated against real logged
tag-to-tag interactions; simulated bots are intentionally not used here.
"""

from __future__ import annotations

from functools import lru_cache
import json
import os
from pathlib import Path
import subprocess
from typing import Any

import pickle


CHUNK_MINUTES = 15
MODEL_BUNDLE_PATH = Path(__file__).resolve().parent.parent.parent / "assets" / "ML" / "final_model_bundle.pkl"
MODEL_SKLEARN_VERSION = "1.2.2"
BACKEND_ROOT = Path(__file__).resolve().parent.parent
COMPAT_PYTHON_PATH = (
    BACKEND_ROOT / ".conda-ml-compat" / "python.exe"
    if os.name == "nt"
    else BACKEND_ROOT / ".conda-ml-compat" / "bin" / "python"
)
WORKER_SCRIPT_PATH = Path(__file__).resolve().parent / "analytics_worker.py"


def _require_ml_stack():
    try:
        import numpy as np
        import pandas as pd
    except ModuleNotFoundError as exc:
        missing = exc.name or "ml dependencies"
        raise RuntimeError(
            f"RTLS analytics requires {missing}. Install backend requirements to enable the Analytics tab."
        ) from exc
    return np, pd


def _install_sklearn_tree_pickle_compat() -> None:
    """
    Allow sklearn>=1.3 to unpickle decision trees serialized by sklearn 1.2.x.

    The bundled RandomForest was trained with sklearn 1.2.2, whose tree node
    dtype did not yet include the ``missing_go_to_left`` field. Newer sklearn
    expects that field during unpickling, so we adapt legacy node arrays before
    the compiled Tree loader validates them.
    """

    np, _ = _require_ml_stack()
    try:
        from sklearn.tree import _tree
    except ModuleNotFoundError as exc:
        missing = exc.name or "scikit-learn"
        raise RuntimeError(
            f"RTLS analytics could not import the sklearn tree loader because {missing} is not installed."
        ) from exc

    if getattr(_tree, "_brigid_pickle_compat_installed", False):
        return

    original_check_node_ndarray = _tree._check_node_ndarray
    tree_expected_dtype = _tree.NODE_DTYPE
    expected_names = list(tree_expected_dtype.names or [])
    legacy_names = [name for name in expected_names if name != "missing_go_to_left"]

    def _patched_check_node_ndarray(node_ndarray, expected_dtype):
        try:
            return original_check_node_ndarray(node_ndarray, expected_dtype)
        except ValueError:
            node_names = list(node_ndarray.dtype.names or [])
            if (
                expected_dtype == tree_expected_dtype
                and "missing_go_to_left" in expected_names
                and node_names == legacy_names
            ):
                upgraded = np.empty(node_ndarray.shape, dtype=expected_dtype)
                for field_name in legacy_names:
                    upgraded[field_name] = node_ndarray[field_name]
                upgraded["missing_go_to_left"] = np.zeros(node_ndarray.shape, dtype="u1")
                return upgraded
            raise

    _tree._check_node_ndarray = _patched_check_node_ndarray
    _tree._brigid_pickle_compat_installed = True


def _upgrade_legacy_sklearn_objects(bundle: dict[str, Any]) -> dict[str, Any]:
    """
    Fill in estimator attributes introduced after sklearn 1.2.x.

    The bundled model predates some newer runtime-only attributes that sklearn
    now expects during prediction. We add conservative defaults so inference can
    proceed without changing the trained parameters themselves.
    """

    model = bundle.get("model")
    if model is None:
        return bundle

    def _patch_tree_estimator(estimator: Any) -> None:
        if not hasattr(estimator, "monotonic_cst"):
            estimator.monotonic_cst = None

    _patch_tree_estimator(model)
    for estimator in getattr(model, "estimators_", []) or []:
        _patch_tree_estimator(estimator)

    return bundle


def _current_sklearn_version() -> str | None:
    try:
        import sklearn
    except ModuleNotFoundError:
        return None
    return getattr(sklearn, "__version__", None)


def _run_compat_worker(csv_path: str) -> dict[str, Any]:
    if not COMPAT_PYTHON_PATH.exists():
        raise RuntimeError(
            "The RTLS analytics model was built with scikit-learn 1.2.2, but the current backend "
            f"runtime has scikit-learn {_current_sklearn_version() or 'missing'}. "
            f"Run `backend/.venv/bin/python backend/setup_backend.py --ensure-ml-compat` "
            f"to create the compatibility runtime at {COMPAT_PYTHON_PATH.parent}."
        )

    env = dict(os.environ)
    env["PYTHONPATH"] = (
        str(BACKEND_ROOT)
        if not env.get("PYTHONPATH")
        else f"{BACKEND_ROOT}{os.pathsep}{env['PYTHONPATH']}"
    )
    try:
        completed = subprocess.run(
            [str(COMPAT_PYTHON_PATH), str(WORKER_SCRIPT_PATH), csv_path],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip() or "Compatibility analytics worker failed."
        raise RuntimeError(detail) from exc

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Compatibility analytics worker returned invalid JSON.") from exc

    if not payload.get("success", False):
        raise RuntimeError(payload.get("error") or "Compatibility analytics worker failed.")
    return payload


@lru_cache(maxsize=1)
def _load_model_bundle() -> dict[str, Any]:
    if not MODEL_BUNDLE_PATH.exists():
        raise FileNotFoundError(f"Model bundle not found at {MODEL_BUNDLE_PATH}")
    try:
        _install_sklearn_tree_pickle_compat()
        with MODEL_BUNDLE_PATH.open("rb") as handle:
            bundle = pickle.load(handle)
        return _upgrade_legacy_sklearn_objects(bundle)
    except ModuleNotFoundError as exc:
        missing = exc.name or "scikit-learn"
        raise RuntimeError(
            f"RTLS analytics could not load the model bundle because {missing} is not installed."
        ) from exc


def _risk_band(probability: float) -> str:
    if probability >= 0.85:
        return "Critical"
    if probability >= 0.65:
        return "High"
    if probability >= 0.35:
        return "Elevated"
    return "Low"


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return value.isoformat()
    except AttributeError:
        return str(value)


def _analyze_csv_log_local(csv_path: str) -> dict[str, Any]:
    np, pd = _require_ml_stack()
    bundle = _load_model_bundle()

    csv_file = Path(csv_path).expanduser()
    if not csv_file.exists():
        raise FileNotFoundError(f"CSV log not found: {csv_file}")

    try:
        raw_df = pd.read_csv(csv_file)
    except Exception as exc:
        raise RuntimeError(f"Could not read CSV log: {exc}") from exc

    required_columns = {"Timestamp", "Tag1", "Tag2", "Distance_ft", "Delta_s"}
    missing_columns = [column for column in required_columns if column not in raw_df.columns]
    if missing_columns:
        raise ValueError(
            "CSV log is missing required columns: " + ", ".join(sorted(missing_columns))
        )

    df = raw_df.loc[:, ["Timestamp", "Tag1", "Tag2", "Distance_ft", "Delta_s"]].copy()
    df["Distance_ft"] = pd.to_numeric(
        df["Distance_ft"].astype(str).str.extract(r"([-+]?\d*\.?\d+)")[0],
        errors="coerce",
    )
    df["Delta_s"] = pd.to_numeric(
        df["Delta_s"].astype(str).str.extract(r"([-+]?\d*\.?\d+)")[0],
        errors="coerce",
    )
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], format="%m.%d.%Y %H:%M:%S", errors="coerce")
    df["Tag1"] = df["Tag1"].astype(str).str.strip()
    df["Tag2"] = df["Tag2"].astype(str).str.strip()
    df = df.dropna(subset=["Timestamp", "Distance_ft", "Delta_s"])
    df = df[(df["Tag1"] != "") & (df["Tag2"] != "") & (df["Delta_s"] >= 0)].copy()

    if df.empty:
        raise ValueError("CSV log does not contain any valid distance rows yet.")

    pair_tags = np.sort(df[["Tag1", "Tag2"]].to_numpy(dtype=str), axis=1)
    df["tag_a"] = pair_tags[:, 0]
    df["tag_b"] = pair_tags[:, 1]
    df["pair"] = df["tag_a"] + " ↔ " + df["tag_b"]
    df["dist_m"] = df["Distance_ft"] * 0.3048
    df["time_chunk"] = df["Timestamp"].dt.floor(f"{CHUNK_MINUTES}min")
    df = df.sort_values(["pair", "time_chunk", "Timestamp"]).reset_index(drop=True)

    start_time = df["Timestamp"].min()
    df["close_contact_seconds"] = np.where(df["dist_m"] < 2.0, df["Delta_s"], 0.0)
    df["kernel_weight_sum"] = np.where(df["dist_m"] <= 5.0, np.exp(-1.5 * df["dist_m"]) * df["Delta_s"], 0.0)
    df["kernel_weight_total"] = np.where(df["dist_m"] <= 5.0, df["Delta_s"], 0.0)

    grouped = (
        df.groupby(["pair", "tag_a", "tag_b", "time_chunk"], sort=True)
        .agg(
            rows=("Timestamp", "size"),
            first_timestamp=("Timestamp", "min"),
            last_timestamp=("Timestamp", "max"),
            exposure_seconds=("Delta_s", "sum"),
            close_contact_seconds=("close_contact_seconds", "sum"),
            kernel_weight_sum=("kernel_weight_sum", "sum"),
            kernel_weight_total=("kernel_weight_total", "sum"),
            mean_distance_ft=("Distance_ft", "mean"),
            min_distance_ft=("Distance_ft", "min"),
        )
        .reset_index()
    )

    if grouped.empty:
        raise ValueError("CSV log does not contain any analyzable exposure windows yet.")

    grouped["close_contact_hours"] = grouped["close_contact_seconds"] / 3600.0
    grouped["total_exposure_hours"] = grouped["exposure_seconds"] / 3600.0
    grouped["num_close_contacts"] = (grouped["close_contact_seconds"] > 0).astype(int)
    grouped["avg_cumulative_contact_hours"] = grouped.groupby("pair")["close_contact_hours"].cumsum()
    grouped["daily_infection_pressure"] = np.where(
        grouped["kernel_weight_total"] > 0,
        (grouped["kernel_weight_sum"] / grouped["kernel_weight_total"]) * 0.6 * 24.0,
        0.0,
    )
    grouped["time_step"] = (
        (grouped["time_chunk"] - start_time).dt.total_seconds() / (CHUNK_MINUTES * 60.0)
    ).astype(int)
    grouped["day"] = (grouped["time_chunk"] - start_time).dt.total_seconds() / (24.0 * 3600.0)
    grouped["shift"] = 0
    grouped["work_zone"] = 0
    grouped["x"] = 0
    grouped["y"] = 0
    grouped["state"] = 0

    feature_defaults = {
        "time_step": 0,
        "day": 0.0,
        "shift": 0,
        "work_zone": 0,
        "x": 0,
        "y": 0,
        "state": 0,
        "num_close_contacts": 0,
        "avg_cumulative_contact_hours": 0.0,
        "daily_infection_pressure": 0.0,
    }
    feature_names = list(bundle.get("feature_names_in") or [])
    survived_features = list(bundle.get("survived_features") or feature_names)
    if not feature_names or not survived_features:
        raise RuntimeError("Model bundle is missing feature metadata.")

    features_df = grouped.copy()
    for column in feature_names:
        if column not in features_df.columns:
            default_value = feature_defaults.get(column)
            if default_value is None:
                default_value = bundle.get("imputation_means", {}).get(
                    column,
                    bundle.get("imputation_modes", {}).get(column, 0),
                )
            features_df[column] = default_value

    features_df = features_df[feature_names].copy()
    for column, value in (bundle.get("imputation_means") or {}).items():
        if column in features_df.columns:
            features_df[column] = pd.to_numeric(features_df[column], errors="coerce").fillna(value)
    for column, value in (bundle.get("imputation_modes") or {}).items():
        if column in features_df.columns:
            features_df[column] = features_df[column].fillna(value)
    features_df = features_df.replace([np.inf, -np.inf], np.nan).fillna(0)

    scaler = bundle.get("scaler")
    model = bundle.get("model")
    if scaler is None or model is None:
        raise RuntimeError("Model bundle is missing fitted model artifacts.")

    try:
        scaled = scaler.transform(features_df[survived_features])
        scaled_df = pd.DataFrame(scaled, columns=survived_features)
        grouped["transmission_probability"] = model.predict_proba(scaled_df)[:, 1]
        grouped["predicted_positive"] = model.predict(scaled_df).astype(int)
    except Exception as exc:
        raise RuntimeError(f"Model prediction failed: {exc}") from exc

    grouped["transmission_pct"] = grouped["transmission_probability"] * 100.0
    grouped["risk_band"] = grouped["transmission_probability"].apply(_risk_band)
    grouped = grouped.sort_values(
        ["transmission_probability", "daily_infection_pressure", "avg_cumulative_contact_hours"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    top_windows = grouped.head(10).copy()
    top_window_rows = [
        {
            "rank": int(index + 1),
            "pair": row["pair"],
            "tag_a": row["tag_a"],
            "tag_b": row["tag_b"],
            "chunk_start": _iso(row["time_chunk"]),
            "first_seen": _iso(row["first_timestamp"]),
            "last_seen": _iso(row["last_timestamp"]),
            "risk_band": row["risk_band"],
            "probability_pct": round(float(row["transmission_pct"]), 2),
            "predicted_positive": bool(row["predicted_positive"]),
            "close_contact_minutes": round(float(row["close_contact_seconds"]) / 60.0, 2),
            "cumulative_contact_hours": round(float(row["avg_cumulative_contact_hours"]), 3),
            "exposure_minutes": round(float(row["exposure_seconds"]) / 60.0, 2),
            "infection_pressure": round(float(row["daily_infection_pressure"]), 3),
            "mean_distance_ft": round(float(row["mean_distance_ft"]), 2),
            "min_distance_ft": round(float(row["min_distance_ft"]), 2),
        }
        for index, row in top_windows.iterrows()
    ]

    pair_peak_rows = grouped.groupby("pair")["transmission_probability"].idxmax().dropna().astype(int)
    pair_summary = (
        grouped.groupby(["pair", "tag_a", "tag_b"], sort=False)
        .agg(
            max_probability_pct=("transmission_pct", "max"),
            avg_probability_pct=("transmission_pct", "mean"),
            windows_analyzed=("time_chunk", "size"),
            windows_above_50=("transmission_probability", lambda series: int((series >= 0.5).sum())),
            total_close_contact_hours=("close_contact_hours", "sum"),
            total_exposure_hours=("total_exposure_hours", "sum"),
            latest_probability_pct=("transmission_pct", "last"),
        )
        .reset_index()
    )
    pair_peaks = grouped.loc[pair_peak_rows, ["pair", "time_chunk", "risk_band"]].rename(
        columns={"time_chunk": "peak_window", "risk_band": "peak_risk_band"}
    )
    pair_summary = pair_summary.merge(pair_peaks, on="pair", how="left")
    pair_summary = pair_summary.sort_values(
        ["max_probability_pct", "avg_probability_pct", "total_close_contact_hours"],
        ascending=[False, False, False],
    ).head(8)
    pair_rows = [
        {
            "pair": row["pair"],
            "tag_a": row["tag_a"],
            "tag_b": row["tag_b"],
            "max_probability_pct": round(float(row["max_probability_pct"]), 2),
            "avg_probability_pct": round(float(row["avg_probability_pct"]), 2),
            "latest_probability_pct": round(float(row["latest_probability_pct"]), 2),
            "windows_analyzed": int(row["windows_analyzed"]),
            "windows_above_50": int(row["windows_above_50"]),
            "total_close_contact_hours": round(float(row["total_close_contact_hours"]), 3),
            "total_exposure_hours": round(float(row["total_exposure_hours"]), 3),
            "peak_window": _iso(row["peak_window"]),
            "peak_risk_band": row["peak_risk_band"],
        }
        for _, row in pair_summary.iterrows()
    ]

    tag_windows = pd.concat(
        [
            grouped[["time_chunk", "pair", "tag_a", "transmission_pct", "risk_band", "close_contact_hours"]].rename(
                columns={"tag_a": "tag_id"}
            ),
            grouped[["time_chunk", "pair", "tag_b", "transmission_pct", "risk_band", "close_contact_hours"]].rename(
                columns={"tag_b": "tag_id"}
            ),
        ],
        ignore_index=True,
    )
    tag_peak_rows = tag_windows.groupby("tag_id")["transmission_pct"].idxmax().dropna().astype(int)
    tag_summary = (
        tag_windows.groupby("tag_id", sort=False)
        .agg(
            max_probability_pct=("transmission_pct", "max"),
            avg_probability_pct=("transmission_pct", "mean"),
            linked_pairs=("pair", "nunique"),
            total_close_contact_hours=("close_contact_hours", "sum"),
        )
        .reset_index()
    )
    tag_peaks = tag_windows.loc[tag_peak_rows, ["tag_id", "pair", "time_chunk", "risk_band"]].rename(
        columns={"pair": "peak_pair", "time_chunk": "peak_window", "risk_band": "peak_risk_band"}
    )
    tag_summary = tag_summary.merge(tag_peaks, on="tag_id", how="left")
    tag_summary = tag_summary.sort_values(
        ["max_probability_pct", "avg_probability_pct", "total_close_contact_hours"],
        ascending=[False, False, False],
    ).head(8)
    tag_rows = [
        {
            "tag_id": row["tag_id"],
            "max_probability_pct": round(float(row["max_probability_pct"]), 2),
            "avg_probability_pct": round(float(row["avg_probability_pct"]), 2),
            "linked_pairs": int(row["linked_pairs"]),
            "total_close_contact_hours": round(float(row["total_close_contact_hours"]), 3),
            "peak_pair": row["peak_pair"],
            "peak_window": _iso(row["peak_window"]),
            "peak_risk_band": row["peak_risk_band"],
        }
        for _, row in tag_summary.iterrows()
    ]

    trend = (
        grouped.groupby("time_chunk", sort=True)
        .agg(
            peak_probability_pct=("transmission_pct", "max"),
            mean_probability_pct=("transmission_pct", "mean"),
            window_count=("pair", "size"),
        )
        .reset_index()
    )
    trend_rows = [
        {
            "chunk_start": _iso(row["time_chunk"]),
            "peak_probability_pct": round(float(row["peak_probability_pct"]), 2),
            "mean_probability_pct": round(float(row["mean_probability_pct"]), 2),
            "window_count": int(row["window_count"]),
        }
        for _, row in trend.iterrows()
    ]

    unique_tags = sorted(set(df["tag_a"]).union(df["tag_b"]))
    summary = {
        "rows_analyzed": int(len(df)),
        "unique_tags": int(len(unique_tags)),
        "unique_pairs": int(grouped["pair"].nunique()),
        "time_windows": int(len(grouped)),
        "peak_probability_pct": round(float(grouped["transmission_pct"].max()), 2),
        "avg_probability_pct": round(float(grouped["transmission_pct"].mean()), 2),
        "latest_window": _iso(grouped["time_chunk"].max()),
        "highest_tag": tag_rows[0]["tag_id"] if tag_rows else None,
    }

    hottest_window = top_window_rows[0] if top_window_rows else None
    return {
        "csv_path": str(csv_file),
        "generated_at": _iso(pd.Timestamp.utcnow()),
        "chunk_minutes": CHUNK_MINUTES,
        "model_name": bundle.get("model_name", "Transmission Model"),
        "summary": summary,
        "hottest_window": hottest_window,
        "top_windows": top_window_rows,
        "pair_leaderboard": pair_rows,
        "tag_leaderboard": tag_rows,
        "trend": trend_rows,
    }


def analyze_csv_log(csv_path: str) -> dict[str, Any]:
    if _current_sklearn_version() != MODEL_SKLEARN_VERSION:
        return _run_compat_worker(csv_path)
    return _analyze_csv_log_local(csv_path)
