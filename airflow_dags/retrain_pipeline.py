"""Airflow DAG: nightly retrain pipeline."""
from __future__ import annotations

import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
import mlflow
from pathlib import Path

DEFAULT_ARGS = {"owner": "airflow", "retries": 1}
BASE_DIR = Path("/app")

with DAG(
    dag_id="retrain_pipeline",
    schedule_interval="0 3 * * *",  # every night at 03:00
    start_date=pendulum.today("UTC").subtract(days=1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["ml"],
):
    scrape = BashOperator(
        task_id="scrape",
        bash_command="python back_end/store_listings.py --pages 3",
        cwd=str(BASE_DIR),
    )

    prepare_features = BashOperator(
        task_id="prepare_features",
        bash_command="python back_end/prepare_features.py",
        cwd=str(BASE_DIR),
    )

    feast_apply = BashOperator(
        task_id="feast_apply",
        bash_command="feast apply -f feature_repo && feast materialize-incremental $(date +'%Y-%m-%dT%H:%M:%S') -f feature_repo",
        cwd=str(BASE_DIR),
    )

    retrain = BashOperator(
        task_id="retrain_model",
        bash_command="python back_end/train_model_ensemble.py",
        cwd=str(BASE_DIR),
    )

    def register_model():
        mlflow.set_tracking_uri("file:./mlruns")
        # assume latest run is best
        client = mlflow.tracking.MlflowClient()
        experiments = client.list_experiments()
        ex = next((e for e in experiments if e.name == "lgbm_mae"), None)
        if ex:
            runs = client.search_runs(experiment_ids=[ex.experiment_id], order_by=["metrics.mae ASC"], max_results=1)
            if runs:
                best_run_id = runs[0].info.run_id
                model_src = f"runs:/{best_run_id}/model"
                mv = mlflow.register_model(model_uri=model_src, name="price_model")
                client.transition_model_version_stage(name="price_model", version=mv.version, stage="Production", archive_existing_versions=True)

    register_task = PythonOperator(task_id="register_model", python_callable=register_model)

    scrape >> prepare_features >> feast_apply >> retrain >> register_task
