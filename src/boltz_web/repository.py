from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from sqlalchemy import select

from boltz_web.models import Asset, AssetFile, Job, Project
from boltz_web.schemas import AssetOut, JobOut, ProjectOut


def asset_to_out(asset: Asset) -> AssetOut:
    return AssetOut(
        id=asset.id,
        project_id=asset.project_id,
        kind=asset.kind,
        name=asset.name,
        status=asset.status,
        parent_asset_id=asset.parent_asset_id,
        source_type=asset.source_type,
        metadata=asset.metadata_json,
        files=[
            {
                "id": item.id,
                "role": item.role,
                "filename": item.filename,
                "content_type": item.content_type,
                "size_bytes": item.size_bytes,
                "sha256": item.sha256,
            }
            for item in asset.files
        ],
    )


def job_to_out(job: Job) -> JobOut:
    return JobOut(
        id=job.id,
        project_id=job.project_id,
        job_type=job.job_type,
        status=job.status,
        input_asset_ids=job.input_asset_ids,
        output_asset_ids=job.output_asset_ids,
        options=job.options_json,
        result=job.result_json,
        error=job.error,
    )


def add_asset_file(
    db: Session,
    asset: Asset,
    role: str,
    filename: str,
    content_type: str,
    path: Path,
    size_bytes: int,
    sha256: str,
) -> AssetFile:
    asset_file = AssetFile(
        asset_id=asset.id,
        role=role,
        filename=filename,
        content_type=content_type,
        storage_path=str(path),
        size_bytes=size_bytes,
        sha256=sha256,
    )
    db.add(asset_file)
    db.flush()
    return asset_file


def project_to_out(project: Project) -> ProjectOut:
    return ProjectOut(id=project.id, name=project.name)


def ensure_project(db: Session, user_id: str, project_id: str | None = None) -> Project:
    if project_id:
        project = db.get(Project, project_id)
        if project is None or project.user_id != user_id:
            raise ValueError("project not found")
        return project
    project = db.scalar(select(Project).where(Project.user_id == user_id, Project.name == "default"))
    if project is None:
        project = Project(user_id=user_id, name="default")
        db.add(project)
        db.flush()
    return project
