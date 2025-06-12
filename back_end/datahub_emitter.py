"""Utility to emit lineage metadata to DataHub after feature materialize or model training."""
import os
from datahub.emitter.mce_builder import make_dataset_urn, make_lineage_mce
from datahub.emitter.rest_emitter import DatahubRestEmitter

GMS_SERVER = os.getenv("DATAHUB_GMS", "http://datahub-gms:8080")
emitter = DatahubRestEmitter(GMS_SERVER)


def emit_lineage(src: str, dest: str):
    """Emit a dataset lineage edge src -> dest (both as dataset urn strings or table names)."""
    if ":" not in src:
        src_urn = make_dataset_urn("mysql", src)
    else:
        src_urn = src
    if ":" not in dest:
        dest_urn = make_dataset_urn("mysql", dest)
    else:
        dest_urn = dest
    mce = make_lineage_mce(src_urn, dest_urn)
    emitter.emit(mce)
