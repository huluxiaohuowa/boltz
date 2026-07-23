from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path

from fastapi import UploadFile

from boltz_web.config import Settings

SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(name: str) -> str:
    cleaned = SAFE_NAME_RE.sub("_", Path(name).name).strip("._")
    return cleaned or "file"


def user_root(settings: Settings, user_id: str) -> Path:
    root = settings.data_dir / "users" / safe_filename(user_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def asset_root(settings: Settings, user_id: str, project_id: str, asset_id: str) -> Path:
    root = user_root(settings, user_id) / "projects" / project_id / "assets" / asset_id
    root.mkdir(parents=True, exist_ok=True)
    return root


def job_root(settings: Settings, user_id: str, project_id: str, job_id: str) -> Path:
    root = user_root(settings, user_id) / "projects" / project_id / "jobs" / job_id
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_bytes(path: Path, data: bytes) -> tuple[int, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return len(data), hashlib.sha256(data).hexdigest()


def copy_file(src: Path, dst: Path) -> tuple[int, str]:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    data = dst.read_bytes()
    return len(data), hashlib.sha256(data).hexdigest()


async def save_upload(upload: UploadFile, dst: Path) -> tuple[int, str]:
    hasher = hashlib.sha256()
    size = 0
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("wb") as out:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            hasher.update(chunk)
            out.write(chunk)
    return size, hasher.hexdigest()
