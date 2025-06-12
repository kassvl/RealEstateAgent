"""Train initial XGBoost regression model and log to MLflow."""
import os
import pandas as pd
from xgboost import XGBRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
import joblib
import mlflow

DATA_PATH = os.getenv("DATASET_CSV", "./back_end/data/dataset.csv")
MODEL_DIR = os.getenv("MODEL_DIR", "./models")
os.makedirs(MODEL_DIR, exist_ok=True)
MODEL_PATH = os.path.join(MODEL_DIR, "price_model.xgb")

# Load data
print("Loading data from", DATA_PATH)
df = pd.read_csv(DATA_PATH)

features = [
    "area_sqm",
    "rooms",
    "latitude",
    "longitude",
    "year_built",
]

df = df.dropna(subset=features + ["price"])
X = df[features]
y = df["price"]

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

print("Starting MLflow run...")
mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "file:./mlruns"))
with mlflow.start_run(run_name="xgboost_v1"):
    params = dict(n_estimators=400, learning_rate=0.05, max_depth=6, subsample=0.8)
    model = XGBRegressor(**params)
    model.fit(X_train, y_train)
    preds = model.predict(X_test)
    mae = mean_absolute_error(y_test, preds)
    mlflow.log_metric("mae", mae)
    mlflow.log_params(params)

    # Save artifacts
    model.save_model(MODEL_PATH)
    mlflow.log_artifact(MODEL_PATH, artifact_path="model")

print("Model trained and saved to", MODEL_PATH)
