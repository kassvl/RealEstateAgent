"""Ensemble training: LightGBM + XGBoost stacked model with SHAP explainability."""
import os, joblib, mlflow, shap, lightgbm as lgb, pandas as pd, xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
from sklearn.ensemble import StackingRegressor
from back_end.datahub_emitter import emit_lineage

DATA_PATH = os.getenv("DATASET_CSV", "./back_end/data/dataset.csv")
FEATURES = [
    "area_sqm",
    "rooms",
    "latitude",
    "longitude",
    "year_built",
    "floor",
    "h3_index",
]
TARGET = "price"


def load_data():
    df = pd.read_csv(DATA_PATH).dropna(subset=FEATURES + [TARGET])
    X = df[FEATURES]
    y = df[TARGET]
    return train_test_split(X, y, test_size=0.2, random_state=42)


def train():
    X_train, X_valid, y_train, y_valid = load_data()
    lgbm = lgb.LGBMRegressor(objective="regression", n_estimators=300)
    xgbr = xgb.XGBRegressor(objective="reg:squarederror", n_estimators=300)
    ensemble = StackingRegressor(
        estimators=[("lgbm", lgbm), ("xgb", xgbr)], final_estimator=lgb.LGBMRegressor()
    )
    ensemble.fit(X_train, y_train)
    preds = ensemble.predict(X_valid)
    mae = mean_absolute_error(y_valid, preds)
    print("Ensemble MAE", mae)
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "file:./mlruns"))
    with mlflow.start_run(run_name="ensemble"):
        mlflow.log_metric("mae", mae)
        mlflow.sklearn.log_model(ensemble, "model")

    model_dir = os.getenv("MODEL_DIR", "./models")
    os.makedirs(model_dir, exist_ok=True)
    joblib.dump(ensemble, os.path.join(model_dir, "ensemble.pkl"))
    try:
        emit_lineage("feast_offline_store", "ensemble_model")
    except Exception as e:
        print("DataHub emit failed", e)

    # SHAP explainer save (TreeExplainer works because ensemble uses tree models)
    explainer = shap.Explainer(ensemble.predict, X_train, feature_names=FEATURES)
    shap.joblib.dump(explainer, os.path.join(model_dir, "shap_explainer.pkl"))


if __name__ == "__main__":
    train()
