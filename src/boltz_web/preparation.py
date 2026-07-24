from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem.EnumerateStereoisomers import EnumerateStereoisomers, StereoEnumerationOptions
from rdkit.Chem.MolStandardize import rdMolStandardize


AMINO3_TO_1 = {
    "ALA": "A",
    "ARG": "R",
    "ASN": "N",
    "ASP": "D",
    "CYS": "C",
    "GLN": "Q",
    "GLU": "E",
    "GLY": "G",
    "HIS": "H",
    "ILE": "I",
    "LEU": "L",
    "LYS": "K",
    "MET": "M",
    "PHE": "F",
    "PRO": "P",
    "SER": "S",
    "THR": "T",
    "TRP": "W",
    "TYR": "Y",
    "VAL": "V",
    "SEC": "U",
    "PYL": "O",
}


def fetch_pdb(pdb_id: str) -> bytes:
    normalized = pdb_id.strip().upper()
    url = f"https://files.rcsb.org/download/{normalized}.pdb"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.content


def _prepare_mol(mol: Chem.Mol, *, strip_salts: bool = True, neutralize: bool = True, generate_3d: bool = True) -> Chem.Mol:
    prepared = rdMolStandardize.Cleanup(mol)
    if strip_salts:
        prepared = rdMolStandardize.FragmentParent(prepared)
    if neutralize:
        prepared = rdMolStandardize.Uncharger().uncharge(prepared)
    if generate_3d:
        prepared = Chem.AddHs(prepared)
        if prepared.GetNumConformers() == 0:
            embed_status = AllChem.EmbedMolecule(prepared, randomSeed=0xC0FFEE)
            if embed_status != 0:
                AllChem.EmbedMolecule(prepared, randomSeed=0xC0FFEE, useRandomCoords=True)
        try:
            AllChem.MMFFOptimizeMolecule(prepared, maxIters=200)
        except Exception:
            AllChem.UFFOptimizeMolecule(prepared, maxIters=200)
    return prepared


def _enumerate_ligand_variants(mol: Chem.Mol, options: dict[str, Any]) -> list[tuple[str, Chem.Mol]]:
    base = _prepare_mol(
        mol,
        strip_salts=bool(options.get("strip_salts", True)),
        neutralize=bool(options.get("neutralize", True)),
        generate_3d=False,
    )
    max_tautomers = max(1, int(options.get("max_tautomers", 8) or 8))
    max_stereoisomers = max(1, int(options.get("max_stereoisomers", 16) or 16))
    variants: list[tuple[str, Chem.Mol]] = [("parent", base)]

    if options.get("enumerate_tautomers"):
        enumerator = rdMolStandardize.TautomerEnumerator()
        enumerator.SetMaxTautomers(max_tautomers)
        variants = [(f"tautomer_{index + 1}", tautomer) for index, tautomer in enumerate(enumerator.Enumerate(base))]

    if options.get("enumerate_stereo"):
        stereo_variants: list[tuple[str, Chem.Mol]] = []
        stereo_options = StereoEnumerationOptions(tryEmbedding=True, unique=True, maxIsomers=max_stereoisomers)
        for label, variant in variants:
            isomers = list(EnumerateStereoisomers(variant, options=stereo_options))
            if not isomers:
                stereo_variants.append((label, variant))
                continue
            stereo_variants.extend((f"{label}_stereo_{index + 1}", Chem.Mol(isomer)) for index, isomer in enumerate(isomers[:max_stereoisomers]))
        variants = stereo_variants

    if not variants:
        variants = [("parent", base)]
    return variants


def smiles_to_sdf(smiles: list[str], names: list[str] | None = None) -> bytes:
    buffer = io.StringIO()
    writer = Chem.SDWriter(buffer)
    try:
        for index, item in enumerate(smiles):
            mol = Chem.MolFromSmiles(item)
            if mol is None:
                raise ValueError(f"invalid SMILES at index {index}: {item}")
            mol = _prepare_mol(mol)
            mol.SetProp("_Name", (names or [])[index] if names and index < len(names) else f"ligand_{index + 1}")
            writer.write(mol)
    finally:
        writer.close()
    return buffer.getvalue().encode("utf-8")


def _standardize_mol(mol: Chem.Mol) -> Chem.Mol:
    return _prepare_mol(mol, strip_salts=True, neutralize=True, generate_3d=False)


def _mol_to_record(mol: Chem.Mol, index: int) -> dict[str, Any]:
    name = mol.GetProp("_Name").strip() if mol.HasProp("_Name") else f"ligand_{index + 1}"
    smiles = Chem.MolToSmiles(Chem.RemoveHs(mol), isomericSmiles=True)
    formula = ""
    try:
        from rdkit.Chem import rdMolDescriptors

        formula = rdMolDescriptors.CalcMolFormula(mol)
    except Exception:
        formula = ""
    return {
        "index": index,
        "name": name or f"ligand_{index + 1}",
        "smiles": smiles,
        "molblock": Chem.MolToMolBlock(Chem.RemoveHs(mol)),
        "heavy_atom_count": Chem.RemoveHs(mol).GetNumHeavyAtoms(),
        "atom_count": mol.GetNumAtoms(),
        "formal_charge": Chem.GetFormalCharge(mol),
        "formula": formula,
    }


def sdf_to_ligand_records(sdf_data: bytes) -> list[dict[str, Any]]:
    supplier = Chem.ForwardSDMolSupplier(io.BytesIO(sdf_data), removeHs=False)
    records: list[dict[str, Any]] = []
    for index, mol in enumerate(supplier):
        if mol is None:
            continue
        try:
            standardized = _standardize_mol(mol)
            records.append(_mol_to_record(standardized, index))
        except Exception:
            records.append(
                {
                    "index": index,
                    "name": f"ligand_{index + 1}",
                    "smiles": "",
                    "molblock": "",
                    "heavy_atom_count": 0,
                    "atom_count": 0,
                    "formal_charge": 0,
                    "formula": "",
                    "status": "failed",
                },
            )
    return records


def molblock_or_smiles_to_record(smiles: str | None, molblock: str | None, name: str, index: int = 0) -> tuple[bytes, dict[str, Any]]:
    sdf = molblock_or_smiles_to_sdf(smiles, molblock, name)
    records = sdf_to_ligand_records(sdf)
    if not records:
        raise ValueError("ligand could not be parsed after preparation")
    records[0]["index"] = index
    return sdf, records[0]


def pdb_sequences_from_text(pdb_text: str) -> list[dict[str, str]]:
    chains: dict[str, list[str]] = {}
    for line in pdb_text.splitlines():
        if not line.startswith("SEQRES"):
            continue
        chain_id = line[11:12].strip()
        residues = line[19:].split()
        if not chain_id or not residues:
            continue
        chains.setdefault(chain_id, []).extend(residues)
    sequences: list[dict[str, str]] = []
    for chain_id, residues in sorted(chains.items()):
        if not residues:
            continue
        known = sum(1 for residue in residues if residue in AMINO3_TO_1)
        # Some PDB entries expose small-molecule or inhibitor chains in SEQRES.
        # Boltz protein entries should not include those ligand-like chains.
        if known / len(residues) < 0.5:
            continue
        sequences.append({"id": chain_id, "sequence": "".join(AMINO3_TO_1.get(residue, "X") for residue in residues)})
    return sequences


def boltz_yaml_from_components(
    protein_sequences: list[dict[str, str]],
    ligand: dict[str, Any],
    chain_id: str,
    affinity: bool = True,
    pocket: dict[str, Any] | None = None,
) -> tuple[str, list[str]]:
    warnings: list[str] = []
    if not protein_sequences:
        warnings.append("No protein SEQRES records were found; generated YAML contains only the ligand.")
    ligand_smiles = ligand.get("smiles") or ""
    if not ligand_smiles and not ligand.get("ccd"):
        raise ValueError("ligand must include a SMILES or CCD value for Boltz")
    if ligand.get("heavy_atom_count", 0) > 56:
        warnings.append("Ligand has more than 56 heavy atoms; Boltz affinity quality may be reduced.")
    if ligand.get("atom_count", 0) > 128:
        warnings.append("Ligand has more than 128 atoms; Boltz affinity may not support this ligand.")

    lines = ["version: 1", "sequences:"]
    for protein in protein_sequences:
        lines.extend(
            [
                "  - protein:",
                f"      id: {protein['id']}",
                f"      sequence: {protein['sequence']}",
            ],
        )
    lines.extend(["  - ligand:", f"      id: {chain_id}"])
    if ligand.get("ccd"):
        lines.append(f"      ccd: {ligand['ccd']}")
    else:
        escaped = ligand_smiles.replace("'", "''")
        lines.append(f"      smiles: '{escaped}'")
    constraints: list[str] = []
    component = (pocket or {}).get("component") or {}
    if component.get("type") == "residue" and component.get("chain") and component.get("resi"):
        constraints.extend(
            [
                "constraints:",
                "  - pocket:",
                f"      binder: {chain_id}",
                f"      contacts: [[{component['chain']}, {component['resi']}]]",
                "      max_distance: 6",
            ],
        )
    elif pocket:
        warnings.append("Pocket center/box assets are kept in metadata; Boltz pocket constraints require residue/atom contacts.")
    if constraints:
        lines.extend(constraints)
    if affinity:
        lines.extend(["properties:", "  - affinity:", f"      binder: {chain_id}"])
    return "\n".join(lines).rstrip() + "\n", warnings


def prepare_ligand_sdf(sdf_data: bytes, options: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    supplier = Chem.ForwardSDMolSupplier(io.BytesIO(sdf_data), removeHs=False)
    buffer = io.StringIO()
    writer = Chem.SDWriter(buffer)
    stats = {
        "input_molecules": 0,
        "prepared_molecules": 0,
        "failed_molecules": 0,
        "tautomer_enumeration": bool(options.get("enumerate_tautomers", False)),
        "stereo_enumeration": bool(options.get("enumerate_stereo", False)),
        "max_tautomers": int(options.get("max_tautomers", 8) or 8),
        "max_stereoisomers": int(options.get("max_stereoisomers", 16) or 16),
        "engine": "rdkit-standardize-mmff",
    }
    try:
        for index, mol in enumerate(supplier):
            stats["input_molecules"] += 1
            if mol is None:
                stats["failed_molecules"] += 1
                continue
            try:
                name = mol.GetProp("_Name") if mol.HasProp("_Name") else f"ligand_{index + 1}"
                variants = _enumerate_ligand_variants(mol, options)
                for variant_label, variant in variants:
                    prepared = _prepare_mol(
                        variant,
                        strip_salts=False,
                        neutralize=False,
                        generate_3d=bool(options.get("generate_3d", True)),
                    )
                    prepared.SetProp("_Name", name if variant_label == "parent" else f"{name}_{variant_label}")
                    prepared.SetProp("BOLTZ_PREP_VARIANT", variant_label)
                    writer.write(prepared)
                    stats["prepared_molecules"] += 1
            except Exception:
                stats["failed_molecules"] += 1
    finally:
        writer.close()
    data = buffer.getvalue().encode("utf-8")
    if stats["prepared_molecules"] == 0 and stats["input_molecules"] > 0:
        raise ValueError("no ligand molecules could be prepared")
    return data, stats


def molblock_or_smiles_to_sdf(smiles: str | None, molblock: str | None, name: str) -> bytes:
    mol = Chem.MolFromMolBlock(molblock, sanitize=True) if molblock else None
    if mol is None and smiles:
        mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError("drawn ligand must include a valid molblock or SMILES")
    mol = _prepare_mol(mol)
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
        "neutralize": options.get("neutralize", True),
        "enumerate_tautomers": options.get("enumerate_tautomers", False),
        "enumerate_stereo": options.get("enumerate_stereo", False),
        "max_tautomers": options.get("max_tautomers", 8),
        "max_stereoisomers": options.get("max_stereoisomers", 16),
        "generate_3d": options.get("generate_3d", True),
        "status": "worker_or_rdkit_prepared",
        "unsupported_operations": [
            "pH-specific protonation state prediction",
        ],
    }
