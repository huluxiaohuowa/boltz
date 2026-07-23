from __future__ import annotations

import secrets
import shutil
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from boltz_web.config import load_settings
from boltz_web.auth import (
    CurrentUser,
    LoginRequest,
    ProvisionUserRequest,
    RegisterRequest,
    TokenOut,
    UserOut,
    create_token,
    ensure_default_admin,
    get_current_user,
    hash_password,
    require_admin,
    validate_username,
    verify_password,
)
from boltz_web.db import SessionLocal, get_db, init_db
from boltz_web.models import Asset, AssetFile, Job, Project, User
from boltz_web.preparation import (
    fetch_pdb,
    ligand_prepare_metadata,
    molblock_or_smiles_to_sdf,
    prepare_pdb_text,
    protein_prepare_metadata,
    smiles_to_sdf,
    table_to_smiles,
)
from boltz_web.redis_events import list_job_events, publish_job_event, redis_client
from boltz_web.repository import add_asset_file, asset_to_out, ensure_project, job_to_out, project_to_out
from boltz_web.schemas import (
    AssetCopyRequest,
    AssetOut,
    AssetUpdateRequest,
    DrawLigandRequest,
    JobCreateRequest,
    JobOut,
    JobRetryRequest,
    PocketCreateRequest,
    PreparationRequest,
    ProteinPdbRequest,
    ProjectCreateRequest,
    ProjectOut,
    SmilesLigandRequest,
)
from boltz_web.storage import asset_root, copy_file, safe_filename, save_upload, user_root, write_bytes

settings = load_settings()
app = FastAPI(title="Boltz WebApp", version="0.1.0")
static_dir = Path(__file__).with_name("static")


@app.on_event("startup")
def startup() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    redis_client.ping()
    with SessionLocal() as db:
        ensure_default_admin(db)


@app.get("/health")
def health() -> dict[str, str]:
    redis_client.ping()
    return {"status": "ok"}


@app.post("/api/v1/auth/login", response_model=TokenOut)
def login(request: LoginRequest, db: Session = Depends(get_db)) -> TokenOut:
    username = validate_username(request.username)
    user = db.get(User, username)
    if user is None or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid username or password")
    if user.status != "active":
        raise HTTPException(status_code=403, detail=f"user status is {user.status}")
    token = create_token(user)
    return TokenOut(access_token=token, user_id=user.id, is_admin=user.is_admin)


@app.post("/api/v1/auth/register", response_model=UserOut)
def register(request: RegisterRequest, db: Session = Depends(get_db)) -> UserOut:
    username = validate_username(request.username)
    if db.get(User, username) is not None:
        raise HTTPException(status_code=409, detail="username already exists")
    user = User(
        id=username,
        password_hash=hash_password(request.password),
        is_admin=False,
        status="pending",
    )
    db.add(user)
    db.commit()
    return UserOut(id=user.id, is_admin=user.is_admin, status=user.status)


@app.get("/api/v1/admin/users", response_model=list[UserOut])
def list_users(
    _admin: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[UserOut]:
    users = db.scalars(select(User).order_by(User.created_at.desc())).all()
    return [UserOut(id=user.id, is_admin=user.is_admin, status=user.status) for user in users]


@app.post("/api/v1/admin/users/{username}/approve", response_model=UserOut)
def approve_user(
    username: str,
    _admin: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserOut:
    user = db.get(User, validate_username(username))
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    user.status = "active"
    db.commit()
    return UserOut(id=user.id, is_admin=user.is_admin, status=user.status)


@app.post("/api/v1/auth/provision-vos-user", response_model=UserOut)
def provision_vos_user(
    request: ProvisionUserRequest,
    x_provision_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> UserOut:
    if not settings.user_provision_token or x_provision_token != settings.user_provision_token:
        raise HTTPException(status_code=403, detail="invalid provision token")
    username = validate_username(request.username)
    user = db.get(User, username)
    if user is None:
        user = User(
            id=username,
            password_hash=hash_password(secrets.token_urlsafe(24)),
            is_admin=request.is_admin,
            status="active",
        )
        db.add(user)
    else:
        user.status = "active"
        user.is_admin = user.is_admin or request.is_admin
    db.commit()
    return UserOut(id=user.id, is_admin=user.is_admin, status=user.status)


@app.post("/api/v1/projects", response_model=ProjectOut)
def create_project(
    request: ProjectCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectOut:
    name = request.name.strip() or "default"
    project = Project(user_id=current_user.id, name=name)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project_to_out(project)


@app.get("/api/v1/projects", response_model=list[ProjectOut])
def list_projects(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ProjectOut]:
    ensure_project(db, current_user.id)
    db.commit()
    projects = db.scalars(select(Project).where(Project.user_id == current_user.id).order_by(Project.created_at.desc())).all()
    return [project_to_out(project) for project in projects]


@app.delete("/api/v1/projects/{project_id}")
def delete_project(
    project_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    project = db.get(Project, project_id)
    if project is None or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="project not found")

    project_path = user_root(settings, current_user.id) / "projects" / project.id
    asset_ids = db.scalars(
        select(Asset.id).where(Asset.user_id == current_user.id, Asset.project_id == project.id),
    ).all()
    if asset_ids:
        db.execute(delete(AssetFile).where(AssetFile.asset_id.in_(asset_ids)))
    db.execute(delete(Job).where(Job.user_id == current_user.id, Job.project_id == project.id))
    db.execute(delete(Asset).where(Asset.user_id == current_user.id, Asset.project_id == project.id))
    db.execute(delete(Project).where(Project.id == project.id, Project.user_id == current_user.id))
    shutil.rmtree(project_path, ignore_errors=True)
    db.commit()
    return {"status": "deleted"}


@app.post("/api/v1/assets/proteins/pdb", response_model=AssetOut)
def create_protein_from_pdb(
    request: ProteinPdbRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssetOut:
    user_id = current_user.id
    try:
        project = ensure_project(db, user_id, request.project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    pdb_id = request.pdb_id.strip().upper()
    try:
        data = fetch_pdb(pdb_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"failed to fetch PDB {pdb_id}: {exc}") from exc
    asset = Asset(
        user_id=user_id,
        project_id=project.id,
        kind="protein",
        name=request.name or pdb_id,
        source_type="pdb_id",
        metadata_json={"pdb_id": pdb_id},
    )
    db.add(asset)
    db.flush()
    path = asset_root(settings, user_id, project.id, asset.id) / f"{pdb_id}.pdb"
    size, sha = write_bytes(path, data)
    add_asset_file(db, asset, "structure", path.name, "chemical/x-pdb", path, size, sha)
    db.commit()
    db.refresh(asset)
    return asset_to_out(asset)


@app.post("/api/v1/assets/upload", response_model=AssetOut)
async def upload_asset(
    kind: str = Form(...),
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    project_id: str | None = Form(default=None),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssetOut:
    if kind not in {"protein", "ligand", "complex"}:
        raise HTTPException(status_code=400, detail="kind must be protein, ligand, or complex")
    user_id = current_user.id
    try:
        project = ensure_project(db, user_id, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    asset = Asset(
        user_id=user_id,
        project_id=project.id,
        kind=kind,
        name=name or file.filename or kind,
        source_type="upload",
        metadata_json={"original_filename": file.filename},
    )
    db.add(asset)
    db.flush()
    filename = safe_filename(file.filename or f"{kind}.dat")
    path = asset_root(settings, user_id, project.id, asset.id) / filename
    size, sha = await save_upload(file, path)
    add_asset_file(db, asset, "source", filename, file.content_type or "application/octet-stream", path, size, sha)
    db.commit()
    db.refresh(asset)
    return asset_to_out(asset)


@app.post("/api/v1/assets/ligands/smiles", response_model=AssetOut)
def create_ligands_from_smiles(
    request: SmilesLigandRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssetOut:
    user_id = current_user.id
    try:
        project = ensure_project(db, user_id, request.project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        data = smiles_to_sdf(request.smiles, request.names)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    asset = Asset(
        user_id=user_id,
        project_id=project.id,
        kind="ligand",
        name=request.name,
        source_type="smiles",
        metadata_json={"count": len(request.smiles), "smiles": request.smiles},
    )
    db.add(asset)
    db.flush()
    path = asset_root(settings, user_id, project.id, asset.id) / "ligands.sdf"
    size, sha = write_bytes(path, data)
    add_asset_file(db, asset, "structure", path.name, "chemical/x-mdl-sdfile", path, size, sha)
    db.commit()
    db.refresh(asset)
    return asset_to_out(asset)


@app.post("/api/v1/assets/ligands/table", response_model=AssetOut)
async def create_ligands_from_table(
    file: UploadFile = File(...),
    smiles_column: str = Form(...),
    name: str = Form(default="table ligands"),
    project_id: str | None = Form(default=None),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssetOut:
    table_data = await file.read()
    try:
        smiles, names = table_to_smiles(table_data, file.filename or "table.csv", smiles_column)
        sdf_data = smiles_to_sdf(smiles, names)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user_id = current_user.id
    try:
        project = ensure_project(db, user_id, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    asset = Asset(
        user_id=user_id,
        project_id=project.id,
        kind="ligand",
        name=name,
        source_type="table",
        metadata_json={"count": len(smiles), "smiles_column": smiles_column, "original_filename": file.filename},
    )
    db.add(asset)
    db.flush()
    root = asset_root(settings, user_id, project.id, asset.id)
    table_path = root / safe_filename(file.filename or "ligands.csv")
    table_size, table_sha = write_bytes(table_path, table_data)
    add_asset_file(db, asset, "source_table", table_path.name, file.content_type or "text/csv", table_path, table_size, table_sha)
    sdf_path = root / "ligands.sdf"
    sdf_size, sdf_sha = write_bytes(sdf_path, sdf_data)
    add_asset_file(db, asset, "structure", sdf_path.name, "chemical/x-mdl-sdfile", sdf_path, sdf_size, sdf_sha)
    db.commit()
    db.refresh(asset)
    return asset_to_out(asset)


@app.post("/api/v1/assets/ligands/draw", response_model=AssetOut)
def create_ligand_from_draw(
    request: DrawLigandRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssetOut:
    user_id = current_user.id
    try:
        project = ensure_project(db, user_id, request.project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        data = molblock_or_smiles_to_sdf(request.smiles, request.molblock, request.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    asset = Asset(
        user_id=user_id,
        project_id=project.id,
        kind="ligand",
        name=request.name,
        source_type="draw",
        metadata_json={"has_molblock": bool(request.molblock), "smiles": request.smiles},
    )
    db.add(asset)
    db.flush()
    path = asset_root(settings, user_id, project.id, asset.id) / "drawn_ligand.sdf"
    size, sha = write_bytes(path, data)
    add_asset_file(db, asset, "structure", path.name, "chemical/x-mdl-sdfile", path, size, sha)
    db.commit()
    db.refresh(asset)
    return asset_to_out(asset)


@app.post("/api/v1/assets/pockets", response_model=AssetOut)
def create_pocket_asset(
    request: PocketCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssetOut:
    user_id = current_user.id
    protein = db.get(Asset, request.protein_asset_id)
    if protein is None or protein.user_id != user_id or protein.kind not in {"protein", "prepared_protein", "complex"}:
        raise HTTPException(status_code=404, detail="protein asset not found")
    try:
        project = ensure_project(db, user_id, request.project_id or protein.project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if protein.project_id != project.id:
        raise HTTPException(status_code=400, detail="protein asset is not in the selected project")
    asset = Asset(
        user_id=user_id,
        project_id=project.id,
        kind="pocket",
        name=request.name.strip() or "binding pocket",
        parent_asset_id=protein.id,
        source_type="pdb_component",
        metadata_json={
            "operation": "pocket_from_component",
            "protein_asset_id": protein.id,
            "reference": request.reference,
            "center": request.center,
            "box_size": request.box_size,
            "component": request.component,
        },
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset_to_out(asset)


@app.get("/api/v1/assets", response_model=list[AssetOut])
def list_assets(
    project_id: str | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AssetOut]:
    user_id = current_user.id
    filters = [Asset.user_id == user_id]
    if project_id:
        filters.append(Asset.project_id == project_id)
    assets = db.scalars(select(Asset).where(*filters).order_by(Asset.created_at.desc())).all()
    return [asset_to_out(asset) for asset in assets]


@app.get("/api/v1/assets/{asset_id}", response_model=AssetOut)
def get_asset(
    asset_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssetOut:
    user_id = current_user.id
    asset = db.get(Asset, asset_id)
    if asset is None or asset.user_id != user_id:
        raise HTTPException(status_code=404, detail="asset not found")
    return asset_to_out(asset)


@app.patch("/api/v1/assets/{asset_id}", response_model=AssetOut)
def update_asset(
    asset_id: str,
    request: AssetUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssetOut:
    user_id = current_user.id
    asset = db.get(Asset, asset_id)
    if asset is None or asset.user_id != user_id:
        raise HTTPException(status_code=404, detail="asset not found")
    asset.name = request.name.strip()
    db.commit()
    db.refresh(asset)
    return asset_to_out(asset)


@app.post("/api/v1/assets/{asset_id}/copy", response_model=AssetOut)
def copy_asset_to_project(
    asset_id: str,
    request: AssetCopyRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssetOut:
    user_id = current_user.id
    source = db.get(Asset, asset_id)
    if source is None or source.user_id != user_id:
        raise HTTPException(status_code=404, detail="asset not found")
    try:
        project = ensure_project(db, user_id, request.project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    copied = Asset(
        user_id=user_id,
        project_id=project.id,
        kind=source.kind,
        name=(request.name or "").strip() or source.name,
        status=source.status,
        parent_asset_id=source.id,
        source_type=f"copied_from_{source.project_id}",
        metadata_json={
            **(source.metadata_json or {}),
            "copied_from_asset_id": source.id,
            "copied_from_project_id": source.project_id,
        },
    )
    db.add(copied)
    db.flush()
    for source_file in source.files:
        src = Path(source_file.storage_path)
        dst = asset_root(settings, user_id, project.id, copied.id) / safe_filename(source_file.filename)
        size, sha = copy_file(src, dst)
        add_asset_file(db, copied, source_file.role, dst.name, source_file.content_type, dst, size, sha)
    db.commit()
    db.refresh(copied)
    return asset_to_out(copied)


@app.delete("/api/v1/assets/{asset_id}")
def delete_asset(
    asset_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    user_id = current_user.id
    asset = db.get(Asset, asset_id)
    if asset is None or asset.user_id != user_id:
        raise HTTPException(status_code=404, detail="asset not found")
    delete_asset_records_and_files(db, asset, user_id)
    db.commit()
    return {"status": "deleted"}


@app.get("/api/v1/assets/{asset_id}/files/{file_id}/download")
def download_asset_file(
    asset_id: str,
    file_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    user_id = current_user.id
    asset = db.get(Asset, asset_id)
    asset_file = db.get(AssetFile, file_id)
    if asset is None or asset_file is None or asset.user_id != user_id or asset_file.asset_id != asset_id:
        raise HTTPException(status_code=404, detail="file not found")
    path = Path(asset_file.storage_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="stored file missing")
    return FileResponse(path, media_type=asset_file.content_type, filename=asset_file.filename)


def delete_asset_records_and_files(db: Session, asset: Asset, user_id: str) -> None:
    root = asset_root(settings, user_id, asset.project_id, asset.id)
    db.execute(update(Asset).where(Asset.parent_asset_id == asset.id).values(parent_asset_id=None))
    db.execute(delete(AssetFile).where(AssetFile.asset_id == asset.id))
    db.execute(delete(Asset).where(Asset.id == asset.id, Asset.user_id == user_id))
    if root.exists():
        shutil.rmtree(root)


def execute_protein_preparation_job(db: Session, job: Job, source: Asset, output_name: str | None = None) -> Asset:
    user_id = job.user_id
    publish_job_event(user_id, job.id, "running", {"message": "started protein preparation"})
    job.status = "running"
    db.flush()
    structure_file = next((item for item in source.files if item.filename.lower().endswith(".pdb")), source.files[0] if source.files else None)
    if structure_file is None:
        raise ValueError("protein asset has no structure file")
    pdb_text = Path(structure_file.storage_path).read_text(errors="replace")
    prepared_text, stats = prepare_pdb_text(pdb_text, job.options_json or {})
    metadata = {
        **protein_prepare_metadata(job.options_json or {}),
        "status": "completed_text_level",
        "worker_note": "text-level PDB cleanup completed; chemistry-specific steps are reported in unsupported_operations",
        "execution_stats": stats,
        "job_id": job.id,
    }
    asset = Asset(
        user_id=user_id,
        project_id=job.project_id,
        kind="prepared_protein",
        name=(output_name or "").strip() or f"{source.name} prepared",
        parent_asset_id=source.id,
        source_type="protein_preparation",
        metadata_json=metadata,
    )
    db.add(asset)
    db.flush()
    filename = f"{safe_filename(asset.name)}.pdb"
    dst = asset_root(settings, user_id, job.project_id, asset.id) / filename
    size, sha = write_bytes(dst, prepared_text.encode("utf-8"))
    add_asset_file(db, asset, "prepared_structure", dst.name, "chemical/x-pdb", dst, size, sha)
    job.output_asset_ids = [asset.id]
    job.result_json = {
        "output_asset_id": asset.id,
        "output_files": [dst.name],
        "execution_stats": stats,
    }
    job.status = "completed"
    publish_job_event(user_id, job.id, "completed", {"output_asset_id": asset.id, "output_files": [dst.name]})
    return asset


def cleanup_job_outputs(db: Session, job: Job) -> int:
    removed = 0
    for asset_id in list(job.output_asset_ids or []):
        asset = db.get(Asset, asset_id)
        if asset is None or asset.user_id != job.user_id or asset.project_id != job.project_id:
            continue
        delete_asset_records_and_files(db, asset, job.user_id)
        removed += 1
    job.output_asset_ids = []
    job.result_json = {**(job.result_json or {}), "cleanup": {"removed_output_assets": removed}}
    publish_job_event(job.user_id, job.id, "cleanup", {"removed_output_assets": removed})
    return removed


@app.post("/api/v1/preparations/protein", response_model=AssetOut)
def prepare_protein(
    request: PreparationRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssetOut:
    user_id = current_user.id
    source = db.get(Asset, request.asset_id)
    if source is None or source.user_id != user_id or source.kind not in {"protein", "prepared_protein", "complex"}:
        raise HTTPException(status_code=404, detail="protein asset not found")
    try:
        project = ensure_project(db, user_id, request.project_id or source.project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    job = Job(
        user_id=user_id,
        project_id=project.id,
        job_type="preparation",
        status="queued",
        input_asset_ids=[source.id],
        options_json={**request.options, "output_name": request.output_name},
    )
    db.add(job)
    db.flush()
    publish_job_event(user_id, job.id, "queued", {"job_type": job.job_type, "input_asset_ids": job.input_asset_ids})
    try:
        asset = execute_protein_preparation_job(db, job, source, request.output_name)
        db.commit()
        db.refresh(asset)
        return asset_to_out(asset)
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
        job.result_json = {"error": str(exc)}
        publish_job_event(user_id, job.id, "failed", {"error": str(exc)})
        db.commit()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/v1/preparations/ligand", response_model=AssetOut)
def prepare_ligand(
    request: PreparationRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssetOut:
    user_id = current_user.id
    source = db.get(Asset, request.asset_id)
    if source is None or source.user_id != user_id or source.kind != "ligand":
        raise HTTPException(status_code=404, detail="ligand asset not found")
    try:
        project = ensure_project(db, user_id, request.project_id or source.project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    asset = Asset(
        user_id=user_id,
        project_id=project.id,
        kind="prepared_ligand",
        name=(request.output_name or "").strip() or f"{source.name} prepared",
        parent_asset_id=source.id,
        source_type="ligand_preparation",
        metadata_json=ligand_prepare_metadata(request.options),
    )
    db.add(asset)
    db.flush()
    if source.files:
        structure_file = next((item for item in source.files if item.role == "structure"), source.files[0])
        dst = asset_root(settings, user_id, project.id, asset.id) / structure_file.filename
        size, sha = copy_file(Path(structure_file.storage_path), dst)
        add_asset_file(db, asset, "prepared_structure", dst.name, structure_file.content_type, dst, size, sha)
    db.commit()
    db.refresh(asset)
    return asset_to_out(asset)


@app.post("/api/v1/jobs", response_model=JobOut)
def create_job(
    request: JobCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobOut:
    user_id = current_user.id
    try:
        project = ensure_project(db, user_id, request.project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    assets = db.scalars(select(Asset).where(Asset.id.in_(request.input_asset_ids))).all()
    found = {asset.id for asset in assets if asset.user_id == user_id and asset.project_id == project.id}
    missing = sorted(set(request.input_asset_ids) - found)
    if missing:
        raise HTTPException(status_code=404, detail={"missing_asset_ids": missing})
    job = Job(
        user_id=user_id,
        project_id=project.id,
        job_type=request.job_type,
        status="queued",
        input_asset_ids=request.input_asset_ids,
        options_json=request.options,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    publish_job_event(user_id, job.id, "queued", {"job_type": job.job_type})
    return job_to_out(job)


@app.get("/api/v1/jobs", response_model=list[JobOut])
def list_jobs(
    project_id: str | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[JobOut]:
    user_id = current_user.id
    filters = [Job.user_id == user_id]
    if project_id:
        filters.append(Job.project_id == project_id)
    jobs = db.scalars(select(Job).where(*filters).order_by(Job.created_at.desc())).all()
    return [job_to_out(job) for job in jobs]


@app.get("/api/v1/jobs/{job_id}", response_model=JobOut)
def get_job(
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobOut:
    user_id = current_user.id
    job = db.get(Job, job_id)
    if job is None or job.user_id != user_id:
        raise HTTPException(status_code=404, detail="job not found")
    return job_to_out(job)


@app.get("/api/v1/jobs/{job_id}/events")
def get_job_events(
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    user_id = current_user.id
    job = db.get(Job, job_id)
    if job is None or job.user_id != user_id:
        raise HTTPException(status_code=404, detail="job not found")
    return list_job_events(user_id, job_id)


@app.post("/api/v1/jobs/{job_id}/cleanup", response_model=JobOut)
def cleanup_job(
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobOut:
    user_id = current_user.id
    job = db.get(Job, job_id)
    if job is None or job.user_id != user_id:
        raise HTTPException(status_code=404, detail="job not found")
    cleanup_job_outputs(db, job)
    db.commit()
    db.refresh(job)
    return job_to_out(job)


@app.post("/api/v1/jobs/{job_id}/retry", response_model=JobOut)
def retry_job(
    job_id: str,
    request: JobRetryRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobOut:
    user_id = current_user.id
    job = db.get(Job, job_id)
    if job is None or job.user_id != user_id:
        raise HTTPException(status_code=404, detail="job not found")
    if job.job_type != "preparation":
        raise HTTPException(status_code=400, detail="only protein preparation jobs can be retried in this build")
    if not job.input_asset_ids:
        raise HTTPException(status_code=400, detail="job has no input asset")
    if request.cleanup_outputs:
        cleanup_job_outputs(db, job)
    source = db.get(Asset, job.input_asset_ids[0])
    if source is None or source.user_id != user_id:
        raise HTTPException(status_code=404, detail="input asset not found")
    job.status = "queued"
    job.error = None
    job.result_json = {}
    job.output_asset_ids = []
    publish_job_event(user_id, job.id, "queued", {"message": "retry requested"})
    try:
        execute_protein_preparation_job(db, job, source, (job.options_json or {}).get("output_name"))
        db.commit()
        db.refresh(job)
        return job_to_out(job)
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
        job.result_json = {"error": str(exc)}
        publish_job_event(user_id, job.id, "failed", {"error": str(exc)})
        db.commit()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")


def run() -> None:
    uvicorn.run("boltz_web.main:app", host="0.0.0.0", port=8800)


if __name__ == "__main__":
    run()
