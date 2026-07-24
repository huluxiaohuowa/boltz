from __future__ import annotations

import argparse
import hashlib
import importlib
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

from boltz_web.config import load_settings
from boltz_web.db import SessionLocal, init_db
from boltz_web.models import Asset, Job
from boltz_web.preparation import ligand_prepare_metadata, prepare_ligand_sdf
from boltz_web.redis_events import publish_job_event, redis_client
from boltz_web.repository import add_asset_file


SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class ComponentCheck:
    name: str
    module: str | None
    purpose: str
    required: bool = True
    command: str | None = None


COMPONENTS = [
    ComponentCheck("RDKit", "rdkit", "standardization, salts, tautomers, stereoisomers, 3D conformers"),
    ComponentCheck("OpenBabel CLI", None, "format conversion and heavy chemistry fallback", command="obabel"),
    ComponentCheck("OpenBabel Python", "openbabel", "Python binding for OpenBabel workflows", required=False),
    ComponentCheck("Meeko", "meeko", "Vina/AutoDock PDBQT preparation", required=False),
    ComponentCheck("Dimorphite-DL", "dimorphite_dl", "pH-aware protonation state enumeration", required=False),
    ComponentCheck("Redis", "redis", "task events and queue integration"),
    ComponentCheck("SQLAlchemy", "sqlalchemy", "job and asset persistence"),
]


def safe_filename(name: str) -> str:
    cleaned = SAFE_NAME_RE.sub("_", Path(name).name).strip("._")
    return cleaned or "file"


def asset_root(settings, user_id: str, project_id: str, asset_id: str) -> Path:
    root = settings.data_dir / "users" / safe_filename(user_id) / "projects" / project_id / "assets" / asset_id
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_bytes(path: Path, data: bytes) -> tuple[int, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return len(data), hashlib.sha256(data).hexdigest()


def _module_version(module_name: str) -> tuple[bool, str, str]:
    try:
        module = importlib.import_module(module_name)
        return True, str(getattr(module, "__version__", "available")), ""
    except Exception as exc:  # noqa: BLE001 - reported in health output
        return False, "", str(exc)


def _command_version(command: str) -> tuple[bool, str, str]:
    path = shutil.which(command)
    if not path:
        return False, "", f"{command} not found in PATH"
    try:
        result = subprocess.run([command, "-V"], text=True, capture_output=True, timeout=10, check=False)
        version = (result.stdout or result.stderr or path).strip().splitlines()[0]
        return True, version, ""
    except Exception as exc:  # noqa: BLE001 - reported in health output
        return False, "", str(exc)


def component_status() -> list[dict[str, str | bool]]:
    status: list[dict[str, str | bool]] = []
    for item in COMPONENTS:
        if item.command:
            ok, version, error = _command_version(item.command)
        elif item.module:
            ok, version, error = _module_version(item.module)
        else:
            ok, version, error = False, "", "invalid component check"
        status.append(
            {
                "name": item.name,
                "module": item.module or item.command or "",
                "purpose": item.purpose,
                "required": item.required,
                "ok": ok,
                "version": version,
                "error": error,
            },
        )
    return status


def print_status() -> int:
    failed = False
    print("Boltz ligand-prep worker component check")
    for item in component_status():
        state = "ok" if item["ok"] else "missing"
        print(f"- {item['name']}: {state} {item['version']}")
        if item["error"]:
            print(f"  error: {item['error']}")
        if item["required"] and not item["ok"]:
            failed = True
    return 1 if failed else 0


def _ligand_sdf_file(asset: Asset):
    for item in asset.files:
        if item.role in {"structure", "prepared_structure"} and item.filename.lower().endswith(".sdf"):
            return item
    raise ValueError("ligand asset does not include an SDF structure file")


def _run_job(job: Job) -> None:
    settings = load_settings()
    with SessionLocal() as db:
        job = db.get(Job, job.id)
        if job is None or job.status != "queued":
            return
        if not job.input_asset_ids or not job.output_asset_ids:
            job.status = "failed"
            job.error = "ligand preparation job is missing input/output asset ids"
            db.commit()
            return
        source = db.get(Asset, job.input_asset_ids[0])
        output = db.get(Asset, job.output_asset_ids[0])
        if source is None or output is None:
            job.status = "failed"
            job.error = "ligand preparation source or output asset not found"
            db.commit()
            return

        job.status = "running"
        output.status = "running"
        publish_job_event(job.user_id, job.id, "running", {"message": "ligand-prep worker started"})
        db.commit()

        try:
            structure_file = _ligand_sdf_file(source)
            options = job.options_json.get("options") or job.options_json
            prepared_data, stats = prepare_ligand_sdf(Path(structure_file.storage_path).read_bytes(), options)
            dst = asset_root(settings, job.user_id, job.project_id, output.id) / f"{safe_filename(output.name)}.sdf"
            size, sha = write_bytes(dst, prepared_data)
            add_asset_file(db, output, "prepared_structure", dst.name, "chemical/x-mdl-sdfile", dst, size, sha)
            output.status = "ready"
            output.metadata_json = {
                **output.metadata_json,
                **ligand_prepare_metadata(options),
                "execution_stats": stats,
                "execution_engine": "boltz-ligand-prep-worker",
                "worker_platform": os.getenv("BOLTZ_LIGAND_PREP_WORKER_PLATFORM", "unknown"),
            }
            job.status = "completed"
            job.result_json = {"output_asset_id": output.id, "output_files": [dst.name], "execution_stats": stats}
            publish_job_event(job.user_id, job.id, "completed", job.result_json)
            db.commit()
        except Exception as exc:  # noqa: BLE001 - job state should capture the user-facing failure
            job.status = "failed"
            job.error = str(exc)
            job.result_json = {"error": str(exc)}
            output.status = "failed"
            output.metadata_json = {**output.metadata_json, "error": str(exc)}
            publish_job_event(job.user_id, job.id, "failed", {"error": str(exc)})
            db.commit()


def _next_job() -> Job | None:
    with SessionLocal() as db:
        return db.scalar(
            select(Job)
            .where(Job.job_type == "ligand_preparation", Job.status == "queued")
            .order_by(Job.created_at.asc())
            .limit(1),
        )


def watch() -> int:
    exit_requested = False

    def stop(_signum: int, _frame: object) -> None:
        nonlocal exit_requested
        exit_requested = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    check_code = print_status()
    if check_code:
        return check_code
    init_db()
    redis_client.ping()

    platform = os.getenv("BOLTZ_LIGAND_PREP_WORKER_PLATFORM", "unknown")
    poll_seconds = float(os.getenv("BOLTZ_LIGAND_PREP_POLL_SECONDS", "5"))
    print(f"ligand-prep worker ready; platform={platform}; poll_seconds={poll_seconds}", flush=True)
    while not exit_requested:
        job = _next_job()
        if job is None:
            time.sleep(poll_seconds)
            continue
        _run_job(job)
    print("ligand-prep worker stopped", flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Boltz ligand-preparation worker")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="check required preparation components and exit")
    group.add_argument("--watch", action="store_true", help="start the ligand-preparation worker")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.check:
        return print_status()
    if args.watch:
        return watch()
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
