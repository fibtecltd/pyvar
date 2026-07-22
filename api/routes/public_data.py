"""
api/routes/public_data.py — serves status.json / demo-result.json (P8 Task 1/2)

Reasoning:
- Written by the scheduled Lambda in pyvar-cdk/stacks/public_data_stack.py,
  read here through the ordinary eu-west-1 ALB — NOT through a separate
  CloudFront/S3 origin at the edge. The us-east-1 EdgeStack must have no S3
  origin at all (tests/test_data_residency.py check5/check6: GDPR Art. 44 /
  CLAUDE.md §3.4 — the edge is metadata/routing only). Serving these two
  small files from the app itself, reading a private eu-west-1 bucket, keeps
  all data on the EU side of that boundary; CloudFront only ever proxies
  HTTP through the existing default_behavior, exactly like every other
  endpoint.
- Mounted at the bare path (no /api/v1 prefix, alongside /health in
  main.py) — portal/pyvar.js already fetches ``{API_BASE}/public/...``.
- Unauthenticated: this data is intentionally public and non-sensitive
  (aggregate service status, a synthetic demo result).
- Cache-Control mirrors the pattern api/routes/var.py already uses for
  SUCCESS results — CloudFront's existing cache policy respects it
  (edge_stack.py's own docstring), so no new edge cache policy is needed.
- The boto3 S3 call is synchronous; run_in_threadpool keeps it from blocking
  the event loop, the same concern storage/session.py's async engine exists
  to avoid for the DB.
"""

from __future__ import annotations

from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException, Response, status
from starlette.concurrency import run_in_threadpool

from config import get_settings
from storage.s3 import get_s3_client

router = APIRouter(tags=["Public"])
cfg = get_settings()


def _read_object(key: str) -> bytes:
    client = get_s3_client()
    try:
        obj = client.get_object(Bucket=cfg.public_data_bucket, Key=key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("NoSuchKey", "404"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not published yet.") from exc
        raise
    return obj["Body"].read()


async def _serve_public_json(key: str) -> Response:
    body = await run_in_threadpool(_read_object, key)
    return Response(content=body, media_type="application/json", headers={"Cache-Control": "public, max-age=60"})


@router.get("/public/status.json", include_in_schema=False)
async def get_status_json() -> Response:
    return await _serve_public_json("public/status.json")


@router.get("/public/demo-result.json", include_in_schema=False)
async def get_demo_result_json() -> Response:
    return await _serve_public_json("public/demo-result.json")
