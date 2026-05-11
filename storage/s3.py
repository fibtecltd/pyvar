"""
storage/s3.py — PyArrow + boto3 Parquet writer to S3/MinIO

Reasoning:
- The full loss_dist array for 1M simulations is ~8MB as float64.
  Storing this in Redis or PostgreSQL is wasteful and slow.
- Writing to S3/MinIO as Parquet via PyArrow's S3FileSystem is the
  most efficient path: no intermediate file on disk, Arrow buffer
  written directly over the network.
- snappy compression gives ~3x size reduction at minimal CPU cost.
- The DB record (storage/models.py) stores the S3 key so the result
  can be retrieved later even after Redis TTL expiry.
- Presigned URLs let clients download large result files directly from S3
  without routing through the API — saves bandwidth and compute.
"""

from __future__ import annotations

import io
import logging

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from botocore.exceptions import ClientError

from config import get_settings

cfg = get_settings()
logger = logging.getLogger(__name__)


def _get_s3_client():
    """Build boto3 S3 client. Points to MinIO in dev, real AWS in production."""
    kwargs = {
        "region_name": cfg.s3_region,
        "aws_access_key_id": cfg.s3_access_key,
        "aws_secret_access_key": cfg.s3_secret_key,
    }
    if cfg.s3_endpoint_url:                    # MinIO or other S3-compatible
        kwargs["endpoint_url"] = cfg.s3_endpoint_url
    return boto3.client("s3", **kwargs)


def write_result_to_s3(result: dict, task_id: str) -> str:
    """
    Serialise the full VaR result dict to Parquet in memory (no temp file)
    and upload to S3/MinIO.

    Returns the S3 key (stored in the DB for later retrieval).

    PyArrow writes to a BytesIO buffer — the buffer is then uploaded
    via boto3 put_object. This avoids touching the local filesystem,
    which is important for containerised workers with read-only filesystems.
    """
    s3_key = f"results/{task_id[:8]}/{task_id}.parquet"

    schema = pa.schema([
        pa.field("task_id",           pa.string()),
        pa.field("var_pct",           pa.float64()),
        pa.field("var_abs",           pa.float64()),
        pa.field("cvar_pct",          pa.float64()),
        pa.field("cvar_abs",          pa.float64()),
        pa.field("mu",                pa.float64()),
        pa.field("sigma",             pa.float64()),
        pa.field("n_simulations",     pa.int64()),
        pa.field("confidence_level",  pa.float64()),
        pa.field("horizon_days",      pa.int32()),
        pa.field("loss_dist",         pa.list_(pa.float64())),
    ])

    table = pa.table(
        {
            "task_id":          [task_id],
            "var_pct":          [result["var_pct"]],
            "var_abs":          [result["var_abs"]],
            "cvar_pct":         [result["cvar_pct"]],
            "cvar_abs":         [result["cvar_abs"]],
            "mu":               [result["mu"]],
            "sigma":            [result["sigma"]],
            "n_simulations":    [result["n_simulations"]],
            "confidence_level": [result["confidence_level"]],
            "horizon_days":     [result["horizon_days"]],
            "loss_dist":        [result["loss_dist"]],
        },
        schema=schema,
    )

    # Write Parquet to in-memory buffer (no disk I/O)
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    buffer.seek(0)

    client = _get_s3_client()
    client.put_object(
        Bucket=cfg.s3_bucket,
        Key=s3_key,
        Body=buffer.read(),
        ContentType="application/octet-stream",
    )

    logger.info("Result written to S3", extra={"s3_key": s3_key, "task_id": task_id})
    return s3_key


def generate_presigned_url(s3_key: str, expiry_seconds: int = 3600) -> str:
    """
    Generate a presigned URL so clients can download the Parquet result
    directly from S3 without routing through the API.
    Useful for large loss distributions that would bloat the API response.
    """
    client = _get_s3_client()
    try:
        url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": cfg.s3_bucket, "Key": s3_key},
            ExpiresIn=expiry_seconds,
        )
        return url
    except ClientError as exc:
        logger.exception("Failed to generate presigned URL", extra={"s3_key": s3_key})
        raise exc
