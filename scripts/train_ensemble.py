"""Train LightGBM, CatBoost, TabNet and blend with ElasticNet."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import joblib
import mlflow
import numpy as np
import optuna
import pandas as pd
from sklearn.linear_model import ElasticNetCV
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split

import lightgbm as lgb
from catboost import CatBoostRegressor
from pytorch_tabnet.tab_model import TabNetRegressor
import torch

FEATURE_CSV = Path(__file__).resolve().parent.parent / "back_end" / "data" / "features.csv"
DB_URL = os.getenv(
    "DATABASE_URL", "postgresql://realestate:realestate@localhost:5432/realestate"
)
MODEL_DIR = Path(__file__).resolve().parent.parent / "models"
MODEL_DIR.mkdir(exist_ok=True)

mlflow.set_tracking_uri("file:./mlruns")
mlflow.set_experiment("real_estate_ensemble")


def load_data() -> tuple[pd.DataFrame, pd.Series]:
    import sqlalchemy as sa

    df_feat = pd.read_csv(FEATURE_CSV)
    engine = sa.create_engine(DB_URL)
    with engine.begin() as conn:
        prices = pd.read_sql(sa.text("SELECT id AS listing_id, price FROM listings WHERE price IS NOT NULL"), conn)
    df = df_feat.merge(prices, on="listing_id").dropna()
    y = df.pop("price")
    df = df.drop(columns=["listing_id", "event_timestamp", "created"])
    return df, y


def train_lgb(X, y):
    def objective(trial):
        params = {
            "objective": "regression",
            "metric": "mae",
            "learning_rate": trial.suggest_float("lr", 0.01, 0.2, log=True),
            "num_leaves": trial.suggest_int("leaves", 31, 128),
            "feature_fraction": trial.suggest_float("ff", 0.6, 1.0),
            "bagging_fraction": trial.suggest_float("bf", 0.6, 1.0),
            "bagging_freq": 5,
        }
        X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42)
        lgb_train = lgb.Dataset(X_train, y_train)
        lgb_val = lgb.Dataset(X_val, y_val)
        model = lgb.train(params, lgb_train, 500, valid_sets=[lgb_val], early_stopping_rounds=50, verbose_eval=False)
        preds = model.predict(X_val)
        return mean_absolute_error(y_val, preds)

    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=50, show_progress_bar=False)
    best_params = study.best_trial.user_attrs.get("params", study.best_params)
    best_model = lgb.train({**best_params, "objective": "regression", "metric": "mae"}, lgb.Dataset(X, y),  study.best_trial.number + 50)
    return best_model


def train_cat(X, y):
    model = CatBoostRegressor(loss_function="MAE", iterations=500, verbose=False)
    model.fit(X, y)
    return model


def train_tabnet(X, y):
    X_np, y_np = X.values, y.values.reshape(-1, 1)
    model = TabNetRegressor(verbose=0, device_name="cpu")
    model.fit(X_np, y_np, max_epochs=200, patience=20)
    return model


def blend_models(models, X_train, y_train):
    preds = np.column_stack([m.predict(X_train) if hasattr(m, "predict") else m.predict(X_train.values) for m in models])
    blender = ElasticNetCV(cv=5).fit(preds, y_train)
    return blender


def main():
    X, y = load_data()
    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42)

    with mlflow.start_run(run_name=f"ensemble_{datetime.utcnow().isoformat()}"):
        lgb_model = train_lgb(X_train, y_train)
        cat_model = train_cat(X_train, y_train)
        tab_model = train_tabnet(X_train, y_train)

        blender = blend_models([lgb_model, cat_model, tab_model], X_val, y_val)

        final_preds = blender.predict(np.column_stack([
            lgb_model.predict(X_val),
            cat_model.predict(X_val),
            tab_model.predict(X_val.values),
        ]))
        mae = mean_absolute_error(y_val, final_preds)
        mlflow.log_metric("mae", mae)

        # log models
        mlflow.lightgbm.log_model(lgb_model, "lgb_model")
        mlflow.catboost.log_model(cat_model, "cat_model")
        mlflow.pyfunc.log_model("tabnet_model", python_model=tab_model)

        joblib.dump({
            "lgb": lgb_model,
            "cat": cat_model,
            "tab": tab_model,
            "blender": blender,
        }, MODEL_DIR / "ensemble.pkl")
        print("Ensemble MAE", mae)


if __name__ == "__main__":
    torch.set_num_threads(4)
    main()
