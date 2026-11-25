"""MinIO 初始化、备份与恢复辅助脚本。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.minio_storage import backup_objects, restore_objects, safe_object_path


class BackupClient:
    def __init__(self) -> None:
        self.uploads: list[tuple[str, str, str]] = []

    def bucket_exists(self, bucket: str) -> bool:
        return bucket == "eoms"

    def fput_object(self, bucket: str, object_name: str, file_path: str, *, content_type: str) -> None:
        self.uploads.append((bucket, object_name, content_type))
        assert Path(file_path).is_file()


class RestoreClient:
    def __init__(self) -> None:
        self.downloads: list[tuple[str, str]] = []

    def bucket_exists(self, bucket: str) -> bool:
        return bucket == "eoms"

    def list_objects(self, bucket: str, *, recursive: bool):
        assert bucket == "eoms"
        assert recursive is True
        return [
            SimpleNamespace(object_name="company/202611/file.txt", is_dir=False),
            SimpleNamespace(object_name="empty/", is_dir=True),
        ]

    def fget_object(self, bucket: str, object_name: str, file_path: str) -> None:
        self.downloads.append((bucket, object_name))
        Path(file_path).write_text(object_name, encoding="utf-8")


def test_safe_object_path_accepts_nested_objects(tmp_path: Path):
    assert safe_object_path(tmp_path, "company/202611/file.txt") == tmp_path / "company" / "202611" / "file.txt"


@pytest.mark.parametrize("object_name", ["", "/absolute.txt", "../escape.txt", "a/../../escape.txt", "a\\escape.txt"])
def test_safe_object_path_rejects_unsafe_names(tmp_path: Path, object_name: str):
    with pytest.raises(ValueError):
        safe_object_path(tmp_path, object_name)


def test_backup_objects_uploads_relative_keys(tmp_path: Path):
    nested = tmp_path / "company" / "202611"
    nested.mkdir(parents=True)
    (nested / "file.txt").write_text("backup", encoding="utf-8")
    (nested / "image.png").write_bytes(b"png")
    client = BackupClient()

    assert backup_objects(client, "eoms", tmp_path) == 2
    assert {item[1] for item in client.uploads} == {"company/202611/file.txt", "company/202611/image.png"}
    assert all(item[0] == "eoms" for item in client.uploads)


def test_restore_objects_creates_parent_directories(tmp_path: Path):
    client = RestoreClient()

    assert restore_objects(client, "eoms", tmp_path) == 1
    restored = tmp_path / "company" / "202611" / "file.txt"
    assert restored.read_text(encoding="utf-8") == "company/202611/file.txt"
    assert client.downloads == [("eoms", "company/202611/file.txt")]
