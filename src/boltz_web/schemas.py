from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


AssetKind = Literal["protein", "ligand", "complex", "prepared_protein", "prepared_ligand", "result"]


class AssetFileOut(BaseModel):
    id: str
    role: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str


class ProjectCreateRequest(BaseModel):
    name: str = "default"


class ProjectOut(BaseModel):
    id: str
    name: str


class AssetOut(BaseModel):
    id: str
    project_id: str
    kind: str
    name: str
    status: str
    parent_asset_id: str | None
    source_type: str
    metadata: dict[str, Any]
    files: list[AssetFileOut]


class JobOut(BaseModel):
    id: str
    project_id: str
    job_type: str
    status: str
    input_asset_ids: list[str]
    output_asset_ids: list[str]
    options: dict[str, Any]
    result: dict[str, Any]
    error: str | None


class ProteinPdbRequest(BaseModel):
    pdb_id: str = Field(min_length=4, max_length=8)
    name: str | None = None
    project_id: str | None = None


class SmilesLigandRequest(BaseModel):
    smiles: list[str] = Field(min_length=1)
    names: list[str] | None = None
    name: str = "SMILES ligands"
    project_id: str | None = None


class DrawLigandRequest(BaseModel):
    smiles: str | None = None
    molblock: str | None = None
    name: str = "drawn ligand"
    project_id: str | None = None


class PreparationRequest(BaseModel):
    asset_id: str
    project_id: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class JobCreateRequest(BaseModel):
    job_type: Literal["preparation", "structure_prediction", "affinity_prediction", "batch_screening", "visualization"]
    input_asset_ids: list[str] = Field(min_length=1)
    project_id: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)
