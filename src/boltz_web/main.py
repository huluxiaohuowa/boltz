from __future__ import annotations

import secrets
import shutil
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
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
    protein_prepare_metadata,
    smiles_to_sdf,
    table_to_smiles,
)
from boltz_web.redis_events import list_job_events, publish_job_event, redis_client
from boltz_web.repository import add_asset_file, asset_to_out, ensure_project, job_to_out, project_to_out
from boltz_web.schemas import (
    AssetOut,
    AssetUpdateRequest,
    DrawLigandRequest,
    JobCreateRequest,
    JobOut,
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

    assets = db.scalars(
        select(Asset).where(Asset.user_id == current_user.id, Asset.project_id == project.id),
    ).all()
    for asset in assets:
        asset.parent_asset_id = None
    db.flush()
    for asset in assets:
        db.delete(asset)

    jobs = db.scalars(
        select(Job).where(Job.user_id == current_user.id, Job.project_id == project.id),
    ).all()
    for job in jobs:
        db.delete(job)

    project_path = user_root(settings, current_user.id) / "projects" / project.id
    shutil.rmtree(project_path, ignore_errors=True)
    db.delete(project)
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
    root = asset_root(settings, user_id, asset.project_id, asset.id)
    db.delete(asset)
    db.commit()
    if root.exists():
        shutil.rmtree(root)
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
    asset = Asset(
        user_id=user_id,
        project_id=project.id,
        kind="prepared_protein",
        name=(request.output_name or "").strip() or f"{source.name} prepared",
        parent_asset_id=source.id,
        source_type="protein_preparation",
        metadata_json=protein_prepare_metadata(request.options),
    )
    db.add(asset)
    db.flush()
    if source.files:
        src_file = source.files[0]
        dst = asset_root(settings, user_id, project.id, asset.id) / src_file.filename
        size, sha = copy_file(Path(src_file.storage_path), dst)
        add_asset_file(db, asset, "prepared_structure", dst.name, src_file.content_type, dst, size, sha)
    db.commit()
    db.refresh(asset)
    return asset_to_out(asset)


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


app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")


def run() -> None:
    uvicorn.run("boltz_web.main:app", host="0.0.0.0", port=8800)


if __name__ == "__main__":
    run()
