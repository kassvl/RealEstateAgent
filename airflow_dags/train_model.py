"""Airflow DAG to train LightGBM model daily from materialized Feast features."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import subprocess

from airflow import DAG
from airflow.operators.python import PythonOperator

DEFAULT_ARGS = {
    "owner": "ml",
    "depends_on_past": False,
    "retries": 1,
}

dag = DAG(
    dag_id="train_price_model_daily",
    default_args=DEFAULT_ARGS,
    description="Train LightGBM model on latest features and log to MLflow",
    schedule_interval="@daily",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["ml", "training"],
)


def run_training(**_: dict):
    repo_root = Path(__file__).resolve().parent.parent
    script = repo_root / "scripts" / "train_pipeline.py"
    subprocess.run(["python", str(script)], check=True)


with dag:
    train_task = PythonOperator(
        task_id="run_train_pipeline",
        python_callable=run_training,
        execution_timeout=timedelta(minutes=30),
    )
