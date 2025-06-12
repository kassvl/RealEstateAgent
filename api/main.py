"""FastAPI service exposing price prediction endpoint."""
from fastapi import FastAPI, HTTPException
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
import os
from pydantic import BaseModel
import joblib, threading, time
import numpy as np
from xgboost import XGBRegressor
import lightgbm as lgb
import logging
from feast import FeatureStore
import mlflow
from back_end.metrics import SCRAPED_LISTINGS, SCRAPE_ERRORS, REQUEST_LATENCY, start_metrics_server, PREDICTION_COUNT, PREDICTION_MAE
import shap
from pathlib import Path
from back_end.risk import simulate_portfolio_losses, value_at_risk, expected_loss
from back_end.zk_certificate import issue_certificate
from back_end.esg_estimator import estimate_energy_score, estimate_co2_emission
from back_end.open_banking import affordability_score

MODEL_PATH = Path("./models/price_model.xgb")
ENSEMBLE_PATH = Path("./models/ensemble.pkl")

app = FastAPI(title="Real Estate Price API")

# OpenTelemetry setup (Jaeger)
resource = Resource(attributes={SERVICE_NAME: "real-estate-api"})
trace.set_tracer_provider(TracerProvider(resource=resource))
jaeger_exporter = JaegerExporter(agent_host_name=os.getenv("JAEGER_HOST", "localhost"), agent_port=6831)
trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(jaeger_exporter))

# OTLP exporter for Tempo
otlp_endpoint = os.getenv("OTLP_ENDPOINT", "http://tempo:4317")
otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(otlp_exporter))

FastAPIInstrumentor.instrument_app(app)

class PredictionRequest(BaseModel):
    area_sqm: float
    rooms: int
    latitude: float
    longitude: float
    year_built: int | None = None
    floor: int = 0

class RiskRequest(BaseModel):
    exposures: list[float]
    default_probs: list[float]
    alpha: float = 0.99

class FinanceRequest(BaseModel):
    incomes: list[float]
    expenses: list[float]

model = None  # can be xgb/lgb/ensemble dict
is_lgb = False
is_ensemble = False

FEATURES = [
    "area_sqm",
    "rooms",
    "year_built",
    "floor",
    "h3_index",
    # embedding columns concatenated later (MiniLM + CLIP)
]

# Feast store (robust init)
BASE_DIR = Path(__file__).resolve().parent.parent
try:
    store = FeatureStore(repo_path=str(BASE_DIR / "feature_repo"))
except Exception as e:
    logging.warning("Feast FeatureStore could not be initialized: %s", e)
    store = None


def load_model():
    """Attempt to load model; log warning if not present."""
    global model, is_lgb, is_ensemble
    if model is not None:
        return model
    try:
        if ENSEMBLE_PATH.exists():
            import joblib
            model = joblib.load(ENSEMBLE_PATH)
            is_ensemble = True
            logging.info("Ensemble model loaded")
            return model
        if MODEL_PATH.exists():
            model = XGBRegressor()
            model.load_model(str(MODEL_PATH))
            return model
        lgb_path = Path("./models/price_model_lgb.txt")
        if lgb_path.exists():
            is_lgb = True
            model = lgb.Booster(model_file=str(lgb_path))
            return model
        raise FileNotFoundError("Model files not found")
    except Exception as e:
        logging.warning("Model could not be loaded: %s", e)
        model = None
        return None


@app.on_event("startup")
def startup_event():
    try:
        load_model()
    except Exception as e:
        logging.warning("Startup could not load model: %s", e)


@app.post("/predict")
def predict_price(req: PredictionRequest):
    if model is None:
        raise HTTPException(status_code=500, detail="Model not loaded")
    features = np.array([[req.area_sqm, req.rooms, req.latitude, req.longitude, req.year_built or 2000]])
    if is_ensemble:
        lgb_m = model["lgb"]
        cat_m = model["cat"]
        tab_m = model["tab"]
        blender = model["blender"]
        stacked = np.column_stack([
            lgb_m.predict(features),
            cat_m.predict(features),
            tab_m.predict(features),
        ])
        pred = blender.predict(stacked)[0]
    else:
        pred = model.predict(features)[0] if not is_lgb else model.predict(features)[0]
    PREDICTION_COUNT.inc()
    # cannot compute MAE without y_true; maybe future
    return {"predicted_price": round(float(pred), 2)}


@app.get("/predict/by_id/{listing_id}")
def predict_by_id(listing_id: str):
    """Predict price using features pulled from Feast online store."""
    if store is None:
        raise HTTPException(status_code=503, detail="Feature store unavailable")
    try:
        entity_rows = [{"listing_id": listing_id}]
        feat_vector = store.get_online_features(
            entity_rows=entity_rows,
            features=["listing_features:" + f for f in FEATURES if f != "h3_index"]
        ).to_df()
        if feat_vector.empty:
            raise HTTPException(status_code=404, detail="Listing features not found in feature store")

        arr = feat_vector.iloc[0].to_numpy(dtype=float).reshape(1, -1)
        if is_ensemble:
            lgb_m = model["lgb"]
            cat_m = model["cat"]
            tab_m = model["tab"]
            blender = model["blender"]
            stacked = np.column_stack([
                lgb_m.predict(arr),
                cat_m.predict(arr),
                tab_m.predict(arr),
            ])
            pred_val = blender.predict(stacked)[0]
        else:
            pred_val = model.predict(arr)[0] if not is_lgb else model.predict(arr)[0]
        return {"listing_id": listing_id, "predicted_price": round(float(pred_val), 2)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/explain")
def explain(req: PredictionRequest):
    features = np.array(
        [
            req.area_sqm,
            req.rooms,
            req.latitude,
            req.longitude,
            req.year_built,
            req.floor,
            0,
        ]
    ).reshape(1, -1)
    # Load explainer
    if not os.path.exists("models/shap_explainer.pkl"):
        raise HTTPException(status_code=500, detail="SHAP explainer not found")
    explainer = shap.joblib.load("models/shap_explainer.pkl")
    shap_values = explainer(features)
    return {"shap_values": shap_values.values[0].tolist(), "base_value": explainer.expected_value}


# what-if simulation – area & rooms varying
@app.get("/what_if/area")
def what_if_area(area_sqm: float, rooms: int, latitude: float, longitude: float, year_built: int, floor: int = 0):
    areas = np.linspace(area_sqm * 0.5, area_sqm * 1.5, num=10)
    preds = []
    for a in areas:
        x = np.array([a, rooms, latitude, longitude, year_built, floor, 0]).reshape(1, -1)
        preds.append(model.predict(x)[0])
    return {"areas": areas.tolist(), "predictions": preds}


# Risk simulation endpoint
@app.post("/risk/portfolio")
def risk_portfolio(req: RiskRequest):
    if len(req.exposures) != len(req.default_probs):
        raise HTTPException(status_code=400, detail="Length mismatch")
    losses = simulate_portfolio_losses(req.exposures, req.default_probs)
    var = value_at_risk(losses, req.alpha)
    el = expected_loss(req.default_probs, req.exposures)
    return {"value_at_risk": var, "expected_loss": el}


# Fair price score
@app.get("/fair_price")
def fair_price(listing_price: float, predicted_price: float):
    diff_pct = (listing_price - predicted_price) / predicted_price * 100
    return {"fair_price_score": -diff_pct}  # negative diff means underpriced


# ZK certificate endpoint
@app.post("/certificate")
def certificate(req: PredictionRequest):
    cert = issue_certificate(req.dict())
    return cert


# ESG endpoint
@app.get("/esg")
def esg(year_built: int | None = None, heating_type: str | None = None, area_sqm: float = 50):
    score = estimate_energy_score(year_built, heating_type)
    co2 = estimate_co2_emission(area_sqm, score)
    return {"energy_score": score, "co2_estimate": co2}


# Affordability endpoint
@app.post("/affordability")
def affordability(req: FinanceRequest):
    score = affordability_score(req.incomes, req.expenses)
    return {"affordability_score": score}

# Background thread to poll MLflow registry every 10 minutes
def _poll_model():
    global model, is_lgb, is_ensemble
    while True:
        try:
            client = mlflow.tracking.MlflowClient()
            mv = client.get_latest_versions(name="price_model", stages=["Production"])
            if mv:
                model_uri = mv[0].source
                if model_uri.endswith(".xgb") and not is_lgb:
                    m = XGBRegressor(); m.load_model(model_uri)
                    model = m
                elif model_uri.endswith(".txt"):
                    model = lgb.Booster(model_file=model_uri)
                    is_lgb = True
        except Exception:
            pass
        time.sleep(600)

threading.Thread(target=_poll_model, daemon=True).start()
