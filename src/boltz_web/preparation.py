from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from rdkit import Chem
from rdkit.Chem import AllChem


def fetch_pdb(pdb_id: str) -> bytes:
    normalized = pdb_id.strip().upper()
    url = f"https://files.rcsb.org/download/{normalized}.pdb"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.content


def smiles_to_sdf(smiles: list[str], names: list[str] | None = None) -> bytes:
    buffer = io.StringIO()
    writer = Chem.SDWriter(buffer)
    try:
        for index, item in enumerate(smiles):
            mol = Chem.MolFromSmiles(item)
            if mol is None:
                raise ValueError(f"invalid SMILES at index {index}: {item}")
            mol = Chem.AddHs(mol)
            AllChem.EmbedMolecule(mol, randomSeed=0xC0FFEE)
            AllChem.UFFOptimizeMolecule(mol, maxIters=200)
            mol.SetProp("_Name", (names or [])[index] if names and index < len(names) else f"ligand_{index + 1}")
            writer.write(mol)
    finally:
        writer.close()
    return buffer.getvalue().encode("utf-8")


def molblock_or_smiles_to_sdf(smiles: str | None, molblock: str | None, name: str) -> bytes:
    mol = Chem.MolFromMolBlock(molblock, sanitize=True) if molblock else None
    if mol is None and smiles:
        mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError("drawn ligand must include a valid molblock or SMILES")
    mol = Chem.AddHs(mol)
    if mol.GetNumConformers() == 0:
        AllChem.EmbedMolecule(mol, randomSeed=0xC0FFEE)
    AllChem.UFFOptimizeMolecule(mol, maxIters=200)
    mol.SetProp("_Name", name)
    buffer = io.StringIO()
    writer = Chem.SDWriter(buffer)
    try:
        writer.write(mol)
    finally:
        writer.close()
    return buffer.getvalue().encode("utf-8")


def table_to_smiles(table_bytes: bytes, filename: str, smiles_column: str) -> tuple[list[str], list[str]]:
    path = Path(filename)
    if path.suffix.lower() in {".xlsx", ".xls"}:
        frame = pd.read_excel(io.BytesIO(table_bytes))
    else:
        sample = table_bytes[:4096].decode("utf-8", errors="ignore")
        dialect = csv.Sniffer().sniff(sample) if sample.strip() else csv.excel
        frame = pd.read_csv(io.BytesIO(table_bytes), dialect=dialect)
    if smiles_column not in frame.columns:
        raise ValueError(f"SMILES column not found: {smiles_column}")
    smiles = [str(value).strip() for value in frame[smiles_column].dropna().tolist()]
    name_column = "name" if "name" in frame.columns else None
    names = [str(value).strip() for value in frame[name_column].fillna("").tolist()] if name_column else []
    return smiles, names


def protein_prepare_metadata(options: dict[str, Any]) -> dict[str, Any]:
    return {
        "operation": "protein_preparation",
        "remove_waters": options.get("remove_waters", True),
        "keep_metals": options.get("keep_metals", True),
        "keep_cofactors": options.get("keep_cofactors", True),
        "ph": options.get("ph", 7.4),
        "pocket": options.get("pocket", {}),
        "status": "placeholder",
    }


def ligand_prepare_metadata(options: dict[str, Any]) -> dict[str, Any]:
    return {
        "operation": "ligand_preparation",
        "strip_salts": options.get("strip_salts", True),
        "enumerate_tautomers": options.get("enumerate_tautomers", False),
        "enumerate_stereo": options.get("enumerate_stereo", False),
        "generate_3d": options.get("generate_3d", True),
        "status": "placeholder",
    }

