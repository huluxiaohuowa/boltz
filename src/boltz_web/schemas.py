from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


AssetKind = Literal[
    "protein",
    "ligand",
    "complex",
    "prepared_protein",
    "prepared_ligand",
    "prepared_ligand_library",
    "boltz_ligand_input",
    "boltz_prediction_input",
    "pocket",
    "result",
]


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


class AssetUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class AssetCopyRequest(BaseModel):
    project_id: str
    name: str | None = None


class PasswordChangeRequest(BaseModel):
    current_password: str | None = None
    new_password: str = Field(min_length=8, max_length=256)


class JobOut(BaseModel):
    id: str
    project_id: str
    project_name: str = ""
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


class EmptyLigandLibraryRequest(BaseModel):
    name: str = "empty ligand library"
    project_id: str | None = None


class DrawLigandRequest(BaseModel):
    smiles: str | None = None
    molblock: str | None = None
    name: str = "drawn ligand"
    project_id: str | None = None


class LigandEditRequest(BaseModel):
    smiles: str | None = None
    molblock: str | None = None
    name: str = "edited ligand"
    project_id: str | None = None
    edit_reason: str | None = None


class ProteinLigandExtractRequest(BaseModel):
    components: list[dict[str, Any]] = Field(min_length=1)
    target_ligand_asset_id: str | None = None
    name: str = "extracted ligands"
    project_id: str | None = None


class LigandMoleculeOut(BaseModel):
    index: int
    name: str
    smiles: str
    molblock: str = ""
    heavy_atom_count: int = 0
    atom_count: int = 0
    formal_charge: int = 0
    formula: str = ""
    status: str = "ready"


class BoltzInputCreateRequest(BaseModel):
    protein_asset_id: str
    ligand_asset_id: str
    ligand_index: int = 0
    pocket_asset_id: str | None = None
    project_id: str | None = None
    chain_id: str = "B"
    affinity: bool = True
    name: str = "boltz input"


class PreparationRequest(BaseModel):
    asset_id: str
    project_id: str | None = None
    output_name: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class PocketCreateRequest(BaseModel):
    protein_asset_id: str
    name: str = "binding pocket"
    project_id: str | None = None
    reference: str
    center: list[float] = Field(min_length=3, max_length=3)
    box_size: list[float] = Field(min_length=3, max_length=3)
    component: dict[str, Any] = Field(default_factory=dict)


class JobCreateRequest(BaseModel):
    job_type: Literal[
        "preparation",
        "structure_prediction",
        "affinity_prediction",
        "batch_screening",
        "visualization",
        "boltz_input_generation",
    ]
    input_asset_ids: list[str] = Field(min_length=1)
    project_id: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class JobRetryRequest(BaseModel):
    cleanup_outputs: bool = True
