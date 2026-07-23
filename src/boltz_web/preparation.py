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
        "add_hydrogens": options.get("add_hydrogens", True),
        "repair_missing_atoms": options.get("repair_missing_atoms", True),
        "assign_protonation": options.get("assign_protonation", True),
        "remove_altloc": options.get("remove_altloc", True),
        "build_biological_unit": options.get("build_biological_unit", False),
        "validate_geometry": options.get("validate_geometry", True),
        "ph": options.get("ph", 7.4),
        "pocket": options.get("pocket", {}),
        "status": "workflow_configured",
        "worker_note": "structure copied; chemistry execution is delegated to the future preparation worker",
    }


def _component_key_from_line(line: str) -> str:
    resn = line[17:20].strip()
    chain = line[21:22].strip() or "_"
    resi = line[22:26].strip()
    icode = line[26:27].strip()
    return f"{resn}|{chain}|{resi}|{icode}"


def prepare_pdb_text(pdb_text: str, options: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Apply safe text-level PDB cleanup operations.

    This intentionally does not pretend to perform chemical preparation steps
    such as protonation, atom rebuilding, or hydrogen placement. Those require
    dedicated chemistry tools and are reported as pending worker operations.
    """

    delete_chains = set((options.get("chain_cleanup") or {}).get("delete_chains") or [])
    delete_components = {
        item.get("key")
        for item in (options.get("component_cleanup") or {}).get("delete_components") or []
        if item.get("key")
    }
    remove_waters = bool(options.get("remove_waters", True))
    water_names = {"HOH", "WAT", "H2O", "DOD"}

    output_lines: list[str] = []
    stats = {
        "input_lines": 0,
        "output_lines": 0,
        "removed_chains": sorted(delete_chains),
        "removed_component_keys": sorted(delete_components),
        "removed_chain_records": 0,
        "removed_component_records": 0,
        "removed_water_records": 0,
        "unsupported_operations": [],
    }

    for line in pdb_text.splitlines():
        stats["input_lines"] += 1
        record = line[:6]
        is_atom_record = record in {"ATOM  ", "HETATM"}
        if is_atom_record:
            chain = line[21:22].strip() or "_"
            if chain in delete_chains:
                stats["removed_chain_records"] += 1
                continue
            if record == "HETATM":
                component_key = _component_key_from_line(line)
                if component_key in delete_components:
                    stats["removed_component_records"] += 1
                    continue
                if remove_waters and line[17:20].strip() in water_names:
                    stats["removed_water_records"] += 1
                    continue
        output_lines.append(line)

    requested_but_not_text_level = {
        "add_hydrogens": "requires Reduce/OpenBabel/PDBFixer worker",
        "assign_protonation": "requires PropKa/PDB2PQR-style worker",
        "repair_missing_atoms": "requires PDBFixer/Modeller worker",
        "remove_altloc": "requires conformer-aware PDB parser worker",
    }
    for key, reason in requested_but_not_text_level.items():
        if options.get(key):
            stats["unsupported_operations"].append({"operation": key, "reason": reason})

    stats["output_lines"] = len(output_lines)
    prepared = "\n".join(output_lines).rstrip() + "\n"
    return prepared, stats


def ligand_prepare_metadata(options: dict[str, Any]) -> dict[str, Any]:
    return {
        "operation": "ligand_preparation",
        "strip_salts": options.get("strip_salts", True),
        "enumerate_tautomers": options.get("enumerate_tautomers", False),
        "enumerate_stereo": options.get("enumerate_stereo", False),
        "generate_3d": options.get("generate_3d", True),
        "status": "placeholder",
    }
