"""文件存储：生产 MinIO，本地开发降级文件系统。

- 上传分块落盘并按 sha256 去重命名，避免同名覆盖与内存膨胀；
- 下载/预览走鉴权接口，必要时生成短时签名 URL；
- 路径统一使用 ``{company_id}/{yyyymm}/{hash}{suffix}``。
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import BinaryIO

from app.core.config import settings
from app.core.errors import BusinessRuleError
from app.core.logging import get_logger
from app.utils.datetime import now

logger = get_logger("eoms.storage")

_SAFE_SUFFIX = re.compile(r"^\.[A-Za-z0-9]{1,10}$")


@dataclass
class StoredObject:
    object_key: str
    size: int
    sha256: str
    suffix: str


def _suffix_of(filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    return suffix if _SAFE_SUFFIX.match(suffix) else ""


def _minio_client():
    from minio import Minio

    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


def _use_minio() -> bool:
    return settings.storage_backend == "minio"


def _local_path(object_key: str) -> Path:
    base = settings.local_storage_path.resolve()
    target = (base / object_key.lstrip("/")).resolve()
    if not str(target).startswith(str(base)):
        raise BusinessRuleError("非法文件路径")
    return target


def save_stream(
    *,
    company_id: int,
    filename: str,
    stream: BinaryIO,
    content_type: str | None = None,
) -> StoredObject:
    """流式保存上传文件，超过配置大小立即中断并清理。"""
    max_bytes = max(settings.max_upload_mb, 1) * 1024 * 1024
    suffix = _suffix_of(filename)
    digest = hashlib.sha256()
    size = 0
    fd, tmp_name = tempfile.mkstemp(prefix="eoms-upload-")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as tmp:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise BusinessRuleError(f"文件超过 {settings.max_upload_mb}MB 限制")
                digest.update(chunk)
                tmp.write(chunk)
        if size == 0:
            raise BusinessRuleError("上传文件不能为空")
        sha = digest.hexdigest()
        object_key = f"{company_id}/{now().strftime('%Y%m')}/{sha}{suffix}"
        if _use_minio():
            client = _minio_client()
            bucket = settings.minio_bucket
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)
            client.fput_object(
                bucket, object_key, str(tmp_path), content_type=content_type or "application/octet-stream"
            )
        else:
            target = _local_path(object_key)
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.move(str(tmp_path), str(target))
        return StoredObject(object_key=object_key, size=size, sha256=sha, suffix=suffix)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:  # pragma: no cover - Windows 占用兜底
                logger.warning("临时文件清理失败: %s", tmp_path)


def open_object(object_key: str) -> BinaryIO:
    if _use_minio():
        client = _minio_client()
        return client.get_object(settings.minio_bucket, object_key)
    path = _local_path(object_key)
    if not path.exists():
        raise BusinessRuleError("文件不存在或已被清理")
    return path.open("rb")


def read_bytes(object_key: str, limit: int = 50 * 1024 * 1024) -> bytes:
    handle = open_object(object_key)
    try:
        data = handle.read(limit + 1)
    finally:
        handle.close()
    if len(data) > limit:
        raise BusinessRuleError("文件过大，无法在线预览")
    return data


def delete_object(object_key: str) -> None:
    if not object_key:
        return
    if _use_minio():
        try:
            _minio_client().remove_object(settings.minio_bucket, object_key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("MinIO 删除失败 %s: %s", object_key, exc)
        return
    path = _local_path(object_key)
    try:
        if path.exists():
            path.unlink()
    except OSError as exc:  # pragma: no cover
        logger.warning("本地文件删除失败 %s: %s", object_key, exc)


def presigned_url(object_key: str, expires: int | None = None) -> str:
    seconds = expires or settings.presign_expire_seconds
    if _use_minio():
        return _minio_client().presigned_get_object(
            settings.minio_bucket, object_key, expires=timedelta(seconds=seconds)
        )
    # 本地模式由鉴权下载接口提供，返回相对 API 路径
    return f"{settings.api_prefix}/files/download?key={object_key}"


def health() -> dict:
    if _use_minio():
        try:
            return {"backend": "minio", "ok": _minio_client().bucket_exists(settings.minio_bucket)}
        except Exception as exc:  # noqa: BLE001
            return {"backend": "minio", "ok": False, "error": str(exc)}
    base = settings.local_storage_path
    try:
        base.mkdir(parents=True, exist_ok=True)
        return {"backend": "local", "ok": True, "path": str(base)}
    except OSError as exc:  # pragma: no cover
        return {"backend": "local", "ok": False, "error": str(exc)}
