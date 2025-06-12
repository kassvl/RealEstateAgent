"""Airflow DAG: daily drift report using Evidently."""
from __future__ import annotations

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator
from evidently.report import Report
from evidently.metrics import DataDriftPreset, RegressionPerformancePreset
import pandas as pd
from datetime import datetime, timedelta
import os

DATASET_CSV = "./back_end/data/dataset.csv"
REPORT_DIR = "./reports"
os.makedirs(REPORT_DIR, exist_ok=True)


def generate_report(**_):
    df = pd.read_csv(DATASET_CSV)
    df["event_timestamp"] = pd.to_datetime(df["date_created"], errors="coerce")
    df = df.sort_values("event_timestamp")
    ref_end = datetime.utcnow() - timedelta(days=30)
    ref = df[df["event_timestamp"] < ref_end]
    cur = df[df["event_timestamp"] >= ref_end]
    if len(ref) < 100 or len(cur) < 100:
        return
    report = Report(metrics=[DataDriftPreset(), RegressionPerformancePreset(target_column="price")])
    report.run(reference_data=ref, current_data=cur)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M")
    report.save_html(os.path.join(REPORT_DIR, f"drift_{ts}.html"))

with DAG(
    dag_id="drift_report",
    schedule_interval="0 5 * * *",  # 05:00 UTC
    start_date=pendulum.today("UTC").subtract(days=1),
    catchup=False,
    tags=["ml", "monitor"],
):
    PythonOperator(task_id="generate_drift_report", python_callable=generate_report)
