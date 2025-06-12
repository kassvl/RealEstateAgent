"""AutoML training with LightGBM + Optuna."""
import os
import pandas as pd
import numpy as np
import optuna
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
import lightgbm as lgb
import mlflow

DATA_PATH = os.getenv("DATASET_CSV", "./back_end/data/dataset.csv")
FEATURES = [
    "area_sqm",
    "rooms",
    "latitude",
    "longitude",
    "year_built",
    "floor",
    "total_floors",
    "balcony_area",
    "parking_spaces",
]
TARGET = "price"


def load_data():
    df = pd.read_csv(DATA_PATH)
    df = df.dropna(subset=FEATURES + [TARGET])
    X = df[FEATURES]
    y = df[TARGET]
    return train_test_split(X, y, test_size=0.2, random_state=42)


def objective(trial):
    X_train, X_valid, y_train, y_valid = load_data()

    params = {
        "objective": "regression",
        "metric": "mae",
        "verbosity": -1,
        "boosting_type": "gbdt",
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
        "num_leaves": trial.suggest_int("num_leaves", 31, 512),
        "feature_fraction": trial.suggest_float("feature_fraction", 0.6, 1.0),
        "bagging_fraction": trial.suggest_float("bagging_fraction", 0.6, 1.0),
        "bagging_freq": trial.suggest_int("bagging_freq", 1, 10),
        "max_depth": trial.suggest_int("max_depth", 3, 12),
        "min_data_in_leaf": trial.suggest_int("min_data_in_leaf", 20, 200),
    }

    lgb_train = lgb.Dataset(X_train, y_train)
    lgb_valid = lgb.Dataset(X_valid, y_valid, reference=lgb_train)
    model = lgb.train(
        params,
        lgb_train,
        valid_sets=[lgb_valid],
        num_boost_round=1000,
        early_stopping_rounds=100,
        verbose_eval=False,
    )
    preds = model.predict(X_valid)
    return mean_absolute_error(y_valid, preds)


if __name__ == "__main__":
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "file:./mlruns"))
    study = optuna.create_study(direction="minimize", study_name="lgbm_mae")
    study.optimize(objective, n_trials=50, timeout=3600)

    print("Best MAE:", study.best_value)
    print("Best params:", study.best_params)

    # Retrain on full data with best params
    X_train, X_valid, y_train, y_valid = load_data()
    best_params = study.best_params | {
        "objective": "regression",
        "metric": "mae",
    }
    lgb_train = lgb.Dataset(pd.concat([X_train, X_valid]), pd.concat([y_train, y_valid]))
    final_model = lgb.train(best_params, lgb_train, num_boost_round=study.best_trial.user_attrs.get("n_boost_round", 1000))

    MODEL_DIR = os.getenv("MODEL_DIR", "./models")
    os.makedirs(MODEL_DIR, exist_ok=True)
    MODEL_PATH = os.path.join(MODEL_DIR, "price_model_lgb.txt")
    final_model.save_model(MODEL_PATH)
    mlflow.log_artifact(MODEL_PATH, artifact_path="model")
    print("Final model saved to", MODEL_PATH)
