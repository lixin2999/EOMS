#!/usr/bin/env python3
"""使用 MinIO Python SDK 完成 bucket 初始化、备份与恢复。"""

from __future__ import annotations

import argparse
import mimetypes
import os
import time
from pathlib import Path, PurePosixPath

from minio import Minio
from minio.error import S3Error


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"缺少环境变量 {name}")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def build_client() -> Minio:
    endpoint = os.getenv("MINIO_ENDPOINT", "minio:9000").strip()
    if "://" in endpoint:
        raise ValueError("MINIO_ENDPOINT 应为 host:port，不应包含 http:// 或 https://")
    return Minio(
        endpoint,
        access_key=required_env("MINIO_ROOT_USER"),
        secret_key=required_env("MINIO_ROOT_PASSWORD"),
        secure=env_bool("MINIO_SECURE"),
    )


def wait_until_ready(client: Minio, bucket: str, timeout: int = 120) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        try:
            client.bucket_exists(bucket)
            return
        except Exception as exc:  # 启动阶段连接失败需要重试
            last_error = exc
            print(f"等待 MinIO 就绪（{attempt}/60）...", flush=True)
            time.sleep(2)
    detail = f"：{last_error}" if last_error else ""
    raise RuntimeError(f"MinIO 在 {timeout} 秒内未就绪{detail}")


def ensure_bucket(client: Minio, bucket: str) -> None:
    if client.bucket_exists(bucket):
        return
    try:
        client.make_bucket(bucket)
    except S3Error as exc:
        if exc.code not in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
            raise
        if not client.bucket_exists(bucket):
            raise


def backup_objects(client: Minio, bucket: str, root: Path) -> int:
    root.mkdir(parents=True, exist_ok=True)
    if not client.bucket_exists(bucket):
        print(f"MinIO bucket {bucket} 不存在，生成空备份目录", flush=True)
        return 0

    count = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            print(f"跳过符号链接：{path}", flush=True)
            continue
        if not path.is_file():
            continue
        object_name = path.relative_to(root).as_posix()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        client.fput_object(bucket, object_name, str(path), content_type=content_type)
        count += 1
    print(f"MinIO 备份完成：{count} 个对象", flush=True)
    return count


def safe_object_path(root: Path, object_name: str) -> Path:
    if not object_name or "\\" in object_name:
        raise ValueError(f"不安全的对象名称：{object_name!r}")
    relative = PurePosixPath(object_name)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError(f"不安全的对象名称：{object_name!r}")

    target = root.joinpath(*relative.parts)
    try:
        target.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"对象名称越出备份目录：{object_name!r}") from exc
    return target


def restore_objects(client: Minio, bucket: str, root: Path) -> int:
    root.mkdir(parents=True, exist_ok=True)
    ensure_bucket(client, bucket)
    count = 0
    for obj in client.list_objects(bucket, recursive=True):
        if obj.is_dir:
            continue
        target = safe_object_path(root, obj.object_name)
        target.parent.mkdir(parents=True, exist_ok=True)
        client.fget_object(bucket, obj.object_name, str(target))
        count += 1
    print(f"MinIO 恢复完成：{count} 个对象", flush=True)
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "backup", "restore"))
    parser.add_argument("directory", nargs="?", help="backup/restore 使用的本地目录")
    args = parser.parse_args()

    if args.action != "init" and not args.directory:
        parser.error(f"{args.action} 必须指定本地目录")

    client = build_client()
    bucket = os.getenv("MINIO_BUCKET", "eoms").strip() or "eoms"

    if args.action == "init":
        wait_until_ready(client, bucket)
        ensure_bucket(client, bucket)
        print(f"MinIO bucket {bucket} 已就绪", flush=True)
    elif args.action == "backup":
        backup_objects(client, bucket, Path(args.directory))
    else:
        restore_objects(client, bucket, Path(args.directory))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
