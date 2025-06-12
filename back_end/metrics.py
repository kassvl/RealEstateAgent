"""Expose Prometheus metrics via HTTP server."""
from prometheus_client import Counter, Gauge, Summary, Histogram, start_http_server
import threading

SCRAPED_LISTINGS = Counter("scraped_listings_total", "Total listings successfully scraped")
SCRAPE_ERRORS = Counter("scrape_errors_total", "Total scrape errors")
REQUEST_LATENCY = Histogram("fetch_request_seconds", "HTTP fetch latency")
PREDICTION_COUNT = Counter("prediction_count_total", "Total predictions served")
PREDICTION_MAE = Counter("prediction_mae_sum", "Sum of absolute errors for MAE calculation")


def start_metrics_server(port: int = 8000):
    threading.Thread(target=start_http_server, args=(port,), daemon=True).start()
