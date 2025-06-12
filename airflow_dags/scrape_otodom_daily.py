"""Airflow DAG to schedule daily Otodom scraping via Celery task."""
from __future__ import annotations

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable

from celery import Celery
from pathlib import Path
import subprocess

CELERY_BROKER_URL = Variable.get("celery_broker_url", default_var="redis://redis:6379/0")
celery_app = Celery(broker=CELERY_BROKER_URL)


def dispatch_scrape_task(max_pages: int = 3, **_: dict):
    result = celery_app.send_task("back_end.tasks.scrape_otodom_task", args=[max_pages])
    return result.id


def _default_args():
    return {
        "owner": "scraper",
        "depends_on_past": False,
        "retries": 1,
    }


dag = DAG(
    dag_id="scrape_otodom_daily",
    default_args=_default_args(),
    description="Daily scrape of Otodom listings",
    schedule_interval="@daily",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["scraper", "otodom"],
)

# validation callable
def validate_latest(**_: dict):
    repo_root = Path(__file__).resolve().parent.parent
    script = repo_root / "scripts" / "validate_listings.py"
    subprocess.run(["python", str(script)], check=True)

with dag:
    kick_off = PythonOperator(
        task_id="dispatch_scrape_task",
        python_callable=dispatch_scrape_task,
        op_kwargs={"max_pages": 5},
    )

    validate = PythonOperator(
        task_id="validate_scraped_data",
        python_callable=validate_latest,
    )

    materialize = PythonOperator(
        task_id="materialize_core_features",
        python_callable=lambda **_: subprocess.run([
            "python",
            str(Path(__file__).resolve().parent.parent / "scripts" / "materialize_core_features.py"),
        ], check=True),
        execution_timeout=timedelta(minutes=15),
    )

    build_geo = PythonOperator(
        task_id="build_geo_features",
        python_callable=lambda **_: subprocess.run([
            "python",
            str(Path(__file__).resolve().parent.parent / "scripts" / "build_geo_features.py"),
        ], check=True),
        execution_timeout=timedelta(minutes=20),
    )

    materialize_geo = PythonOperator(
        task_id="materialize_geo_features",
        python_callable=lambda **_: subprocess.run([
            "feast",
            "materialize-incremental",
            str(datetime.utcnow().date()),
        ], cwd=str(Path(__file__).resolve().parent.parent / "feature_repo"), check=True),
        execution_timeout=timedelta(minutes=10),
    )

    kick_off >> validate >> materialize >> build_geo >> materialize_geo
