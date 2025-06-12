"""Train LightGBM regression model on latest features and register with MLflow."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import joblib
import mlflow
import mlflow.lightgbm
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error
from sklearn.model_selection import train_test_split
from sqlalchemy import create_engine, text
from mlflow.tracking import MlflowClient

FEATURE_CSV = Path(__file__).resolve().parent.parent / "back_end" / "data" / "features.csv"
DB_URL = os.getenv(
    "DATABASE_URL", "postgresql://realestate:realestate@localhost:5432/realestate"
)
MODEL_DIR = Path(__file__).resolve().parent.parent / "models"
MODEL_DIR.mkdir(exist_ok=True)
MODEL_PATH = MODEL_DIR / "price_model_lgbm.pkl"


def load_dataset() -> pd.DataFrame:
    features = pd.read_csv(FEATURE_CSV)
    if features.empty:
        raise ValueError("Feature CSV is empty – run materialization first.")

    engine = create_engine(DB_URL, pool_pre_ping=True)
    with engine.begin() as conn:
        price_df = pd.read_sql(
            text("SELECT id AS listing_id, price FROM listings WHERE price IS NOT NULL"), conn
        )
    df = features.merge(price_df, on="listing_id", how="inner")
    return df


def train_model(df: pd.DataFrame):
    target = df.pop("price")
    X_train, X_val, y_train, y_val = train_test_split(
        df, target, test_size=0.2, random_state=42, shuffle=True
    )

    train_set = lgb.Dataset(X_train, label=y_train)
    val_set = lgb.Dataset(X_val, label=y_val)

    params = {
        "objective": "regression",
        "metric": "mae",
        "learning_rate": 0.05,
        "num_leaves": 64,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 5,
        "seed": 42,
    }

    model = lgb.train(
        params,
        train_set,
        num_boost_round=500,
        valid_sets=[val_set],
        early_stopping_rounds=30,
        verbose_eval=False,
    )

    preds = model.predict(X_val)
    mae = mean_absolute_error(y_val, preds)
    mape = mean_absolute_percentage_error(y_val, preds)
    return model, mae, mape


def main():
    mlflow.set_tracking_uri("file:./mlruns")
    mlflow.set_experiment("real_estate_pricing")
    with mlflow.start_run(run_name=f"lgbm_{datetime.utcnow().isoformat()}"):
        df = load_dataset()
        model, mae, mape = train_model(df)

        mlflow.log_metric("mae", mae)
        mlflow.log_metric("mape", mape)

        model_info = mlflow.lightgbm.log_model(model, artifact_path="model", registered_model_name="price_model")

        joblib.dump(model, MODEL_PATH)

        client = MlflowClient()
        prod_versions = client.get_latest_versions(name="price_model", stages=["Production"])
        promote = False
        if not prod_versions:
            print("No Production model, promoting current.")
            promote = True
        else:
            prod_v = prod_versions[0]
            prod_mae = float(client.get_metric_history(prod_v.run_id, "mae")[0].value)
            improvement = (prod_mae - mae) / prod_mae
            if improvement >= 0.03:
                print(f"MAE improved by {improvement:.2%}, promoting new model")
                promote = True
            else:
                print(f"MAE improvement {improvement:.2%} < 3%, staying with current model")

        if promote:
            client.transition_model_version_stage(
                name="price_model",
                version=model_info.model_version.version,
                stage="Production",
                archive_existing_versions=True,
            )

        print("MAE", mae, "MAPE", mape)


if __name__ == "__main__":
    main()
