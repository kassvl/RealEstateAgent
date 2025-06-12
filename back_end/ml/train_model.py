"""Train a baseline regression model using the extracted visual features.

Usage:
    python train_model.py --features features.parquet --label price_pln --model model.pkl

Notes:
- Ensure `features.parquet` contains the label column (e.g., target listing price or demand score).
- By default, a LightGBM (if installed) or XGBoost regressor is used; falls back to RandomForest.
- The script logs RMSE on a validation split and saves the fitted model with joblib.
"""
import argparse
import os
import sys
import uuid
from pathlib import Path
from typing import Dict, Any

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor, StackingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_squared_error, mean_absolute_percentage_error
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

# Optional heavy deps
try:
    from lightgbm import LGBMRegressor  # type: ignore

    HAS_LGBM = True
except ImportError:
    HAS_LGBM = False

try:
    from xgboost import XGBRegressor  # type: ignore

    HAS_XGB = True
except ImportError:
    HAS_XGB = False

try:
    import optuna  # type: ignore

    HAS_OPTUNA = True
except ImportError:
    HAS_OPTUNA = False

try:
    import mlflow  # type: ignore

    HAS_MLFLOW = True
except ImportError:
    HAS_MLFLOW = False


def _default_model():
    if HAS_LGBM:
        return LGBMRegressor(n_estimators=500, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8)
    if HAS_XGB:
        return XGBRegressor(n_estimators=500, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8)
    return RandomForestRegressor(n_estimators=400, max_depth=None, n_jobs=-1)


def objective(trial: "optuna.trial.Trial", X_train, X_val, y_train, y_val):
    params: Dict[str, Any] = {
        "n_estimators": trial.suggest_int("n_estimators", 200, 1200),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
        "max_depth": trial.suggest_int("max_depth", 3, 10),
        "subsample": trial.suggest_float("subsample", 0.6, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
    }
    model = LGBMRegressor(**params) if HAS_LGBM else RandomForestRegressor(**params)
    model.fit(X_train, y_train)
    preds = model.predict(X_val)
    rmse = mean_squared_error(y_val, preds, squared=False)
    return rmse


def main(parquet_path: str, label_col: str, model_out: str, test_size: float = 0.2, mode: str = "baseline", hpo: bool = False, hpo_trials: int = 30):
    if not os.path.isfile(parquet_path):
        sys.exit(f"Features file not found: {parquet_path}")

    df = pd.read_parquet(parquet_path)
    if label_col not in df.columns:
        sys.exit(f"Label column '{label_col}' not found in features file.")

    y = df[label_col]
    X = df.drop(columns=[label_col])

    num_cols = X.select_dtypes(include=[float, int]).columns.tolist()
    preprocessor = ColumnTransformer(
        [
            (
                "num",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="median")),
                        ("scaler", StandardScaler()),
                    ]
                ),
                num_cols,
            )
        ],
        remainder="drop",
    )

    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=test_size, random_state=42
    )

    if mode == "baseline":
        model = _default_model()
    elif mode == "ensemble":
        base_models = []
        if HAS_LGBM:
            base_models.append(("lgbm", LGBMRegressor(n_estimators=600)))
        if HAS_XGB:
            base_models.append(("xgb", XGBRegressor(n_estimators=600)))
        base_models.append(("rf", RandomForestRegressor(n_estimators=500)))
        model = StackingRegressor(
            estimators=base_models,
            final_estimator=RandomForestRegressor(n_estimators=300),
        )
    else:
        sys.exit(f"Unsupported mode: {mode}")

    pipeline = Pipeline([("prep", preprocessor), ("model", model)])

    # ---------------- Hyperparameter tuning (Optuna) ----------------
    if hpo and mode == "baseline" and HAS_OPTUNA and HAS_LGBM:
        study = optuna.create_study(direction="minimize")
        study.optimize(
            lambda tr: objective(tr, X_train, X_val, y_train, y_val),
            n_trials=hpo_trials,
            show_progress_bar=True,
        )
        best_params = study.best_params
        model = LGBMRegressor(**best_params)
        pipeline = Pipeline([("prep", preprocessor), ("model", model)])

    # ---------------- Training ----------------
    pipeline.fit(X_train, y_train)
    preds = pipeline.predict(X_val)
    rmse = mean_squared_error(y_val, preds, squared=False)
    mape = mean_absolute_percentage_error(y_val, preds)
    print(f"Validation -> RMSE: {rmse:.3f} | MAPE: {mape*100:.2f}%")

    # ---------------- Tracking ----------------
    if HAS_MLFLOW:
        with mlflow.start_run(run_name=f"{mode}_{uuid.uuid4().hex[:6]}"):
            mlflow.log_param("mode", mode)
            mlflow.log_param("rows", len(df))
            if HAS_OPTUNA and hpo and mode == "baseline":
                mlflow.log_params(best_params)  # type: ignore # noqa
            mlflow.log_metric("rmse", rmse)
            mlflow.log_metric("mape", mape)
            mlflow.sklearn.log_model(pipeline, artifact_path="model")

    # ---------------- Persist ----------------
    Path(model_out).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, model_out)
    print(f"Model saved to {model_out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", required=True, help="Path to feature parquet/CSV file")
    parser.add_argument("--label", required=True, help="Target column name")
    parser.add_argument("--model", default="models/price_model.pkl", help="Output model path")
    parser.add_argument("--mode", default="baseline", choices=["baseline", "ensemble"], help="Training mode")
    parser.add_argument("--test_size", type=float, default=0.2, help="Validation split ratio")
    parser.add_argument("--hpo", action="store_true", help="Enable Optuna HPO (baseline mode only)")
    parser.add_argument("--hpo_trials", type=int, default=30, help="Number of Optuna trials")
    args = parser.parse_args()

    main(
        parquet_path=args.features,
        label_col=args.label,
        model_out=args.model,
        test_size=args.test_size,
        mode=args.mode,
        hpo=args.hpo,
        hpo_trials=args.hpo_trials,
    )
