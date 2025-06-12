"""Quick script to train a dummy XGBoost model and save to models/price_model.xgb.
Run once locally to generate a placeholder model so that the API can start without training pipeline.
"""

import os
from pathlib import Path
import numpy as np
from xgboost import XGBRegressor

# parameters
n_samples = 500
n_features = 5

rng = np.random.default_rng(42)
X = rng.normal(size=(n_samples, n_features))
# simple linear-ish target with noise
coeffs = rng.uniform(10, 100, size=(n_features,))
y = X @ coeffs + rng.normal(scale=5.0, size=n_samples)

model = XGBRegressor(n_estimators=50, max_depth=3, learning_rate=0.1, objective="reg:squarederror")
model.fit(X, y)

models_dir = Path(__file__).parent / "models"
models_dir.mkdir(exist_ok=True)
model_path = models_dir / "price_model.xgb"
model.save_model(str(model_path))

print(f"Dummy model trained and saved to {model_path}")
