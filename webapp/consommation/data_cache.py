"""
Local Parquet cache for S3 files.

Downloads each Parquet file from S3 once, stores it in PARQUET_CACHE_DIR
(default /tmp/parquet_cache), and re-checks the S3 ETag at most once per
PARQUET_CACHE_CHECK_TTL seconds (default 3600).  On ETag change the file is
re-downloaded atomically.

Usage in services:
    from . import data_cache
    path = data_cache.get_local_path('puissance')   # str, local or s3:// fallback
"""

import json
import logging
import os
import threading
import time
from pathlib import Path

import boto3
from django.conf import settings

logger = logging.getLogger(__name__)

# Per-key locks to avoid concurrent downloads of the same file
_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


def _get_lock(key: str) -> threading.Lock:
    with _locks_lock:
        if key not in _locks:
            _locks[key] = threading.Lock()
        return _locks[key]


def _parse_s3_path(s3_path: str) -> tuple[str, str]:
    """Parse 's3://bucket/key/file.parquet' → ('bucket', 'key/file.parquet')."""
    if not s3_path or not s3_path.startswith("s3://"):
        return "", ""
    path = s3_path[5:]
    parts = path.split("/", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (parts[0], "")


def _cache_dir() -> Path:
    return Path(getattr(settings, "PARQUET_CACHE_DIR", "/tmp/parquet_cache"))


def _local_path(key: str) -> Path:
    filename = os.path.basename(settings.S3_PATHS[key])
    return _cache_dir() / filename


def _meta_path(key: str) -> Path:
    filename = os.path.basename(settings.S3_PATHS[key])
    return _cache_dir() / (filename + ".meta.json")


def _read_meta(key: str) -> dict:
    meta_file = _meta_path(key)
    if meta_file.exists():
        try:
            with open(meta_file) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _write_meta(key: str, etag: str) -> None:
    with open(_meta_path(key), "w") as f:
        json.dump({"etag": etag, "checked_at": time.time()}, f)


def _s3_client():
    return boto3.client(
        "s3",
        region_name=settings.AWS_CONFIG["region"],
        aws_access_key_id=settings.AWS_CONFIG["access_key"],
        aws_secret_access_key=settings.AWS_CONFIG["secret_key"],
    )


def _download(key: str) -> None:
    """Download the Parquet file for *key* from S3, atomically."""
    s3_path = settings.S3_PATHS[key]
    bucket, s3_key = _parse_s3_path(s3_path)
    if not bucket:
        logger.warning("Invalid S3 path for key %s: %s", key, s3_path)
        return

    _cache_dir().mkdir(parents=True, exist_ok=True)

    local = _local_path(key)
    tmp = local.with_suffix(".parquet.tmp")

    client = _s3_client()
    head = client.head_object(Bucket=bucket, Key=s3_key)
    etag = head.get("ETag", "")

    logger.info("Downloading parquet key=%s from S3…", key)
    client.download_file(bucket, s3_key, str(tmp))
    tmp.rename(local)  # atomic on POSIX
    _write_meta(key, etag)
    logger.info("Cached parquet key=%s at %s", key, local)


def ensure_local_parquet(key: str) -> str:
    """
    Ensure the local Parquet for *key* is present and not stale.

    - If the file exists and was checked within PARQUET_CACHE_CHECK_TTL: return local path.
    - Otherwise: call head_object on S3.  If ETag unchanged: refresh timestamp, return local.
    - If ETag changed or file missing: (re-)download, return local path.
    - On any error: return local path if available, else S3 URL as fallback.
    """
    s3_path = settings.S3_PATHS.get(key)
    if not s3_path:
        return s3_path  # type: ignore[return-value]

    ttl: int = getattr(settings, "PARQUET_CACHE_CHECK_TTL", 3600)
    local = _local_path(key)
    meta = _read_meta(key)
    now = time.time()

    # Fast path: file present and checked recently
    if local.exists() and meta.get("checked_at", 0) + ttl > now:
        return str(local)

    # Slow path: need to check or download — hold a per-key lock
    lock = _get_lock(key)
    with lock:
        # Re-read inside the lock: another thread may have just finished
        meta = _read_meta(key)
        if local.exists() and meta.get("checked_at", 0) + ttl > now:
            return str(local)

        try:
            bucket, s3_key = _parse_s3_path(s3_path)
            if not bucket:
                return s3_path

            client = _s3_client()
            head = client.head_object(Bucket=bucket, Key=s3_key)
            remote_etag = head.get("ETag", "")

            if local.exists() and meta.get("etag") == remote_etag:
                # Up to date — just refresh the timestamp to avoid re-checking for ttl seconds
                _write_meta(key, remote_etag)
                return str(local)

            # New data: re-download
            _download(key)
            return str(local)

        except Exception:
            logger.exception("Failed to check/download parquet for key=%s", key)
            # Graceful degradation: local stale copy or original S3 URL
            return str(local) if local.exists() else s3_path


def get_local_path(key: str) -> str:
    """Return a ready-to-use parquet path for *key* (local path or s3:// fallback)."""
    return ensure_local_parquet(key)


def refresh_all(force: bool = False) -> None:
    """Download/refresh all parquet files declared in settings.S3_PATHS."""
    for key in settings.S3_PATHS:
        try:
            if force:
                meta_file = _meta_path(key)
                local = _local_path(key)
                if meta_file.exists():
                    meta_file.unlink()
                if local.exists():
                    local.unlink()
            ensure_local_parquet(key)
        except Exception:
            logger.exception("refresh_all failed for key=%s", key)
