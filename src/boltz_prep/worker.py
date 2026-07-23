from __future__ import annotations

import argparse
import importlib
import os
import signal
import sys
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class ComponentCheck:
    name: str
    module: str
    purpose: str
    required: bool = True


COMPONENTS = [
    ComponentCheck("Gemmi", "gemmi", "fast PDB/mmCIF parsing, component selection, and structure writing"),
    ComponentCheck("OpenMM", "openmm", "molecular mechanics backend used by PDBFixer"),
    ComponentCheck("PDBFixer", "pdbfixer", "missing atom/residue repair and structure normalization"),
    ComponentCheck("PropKa", "propka", "pH-aware protonation state estimation"),
    ComponentCheck("PDB2PQR", "pdb2pqr", "PQR generation and protonation workflow integration"),
    ComponentCheck("RDKit", "rdkit", "ligand/cofactor chemistry checks"),
    ComponentCheck("MDAnalysis", "MDAnalysis", "trajectory/structure selections and neighborhood analysis"),
    ComponentCheck("NumPy", "numpy", "vectorized pocket and neighborhood calculations"),
    ComponentCheck("Redis", "redis", "worker queue and task event integration"),
    ComponentCheck("SQLAlchemy", "sqlalchemy", "metadata and task database integration"),
]


def component_status() -> list[dict[str, str | bool]]:
    status: list[dict[str, str | bool]] = []
    for item in COMPONENTS:
        try:
            module = importlib.import_module(item.module)
            version = getattr(module, "__version__", "available")
            ok = True
            error = ""
        except Exception as exc:  # noqa: BLE001 - report import failure directly for health checks
            version = ""
            ok = False
            error = str(exc)
        status.append(
            {
                "name": item.name,
                "module": item.module,
                "purpose": item.purpose,
                "required": item.required,
                "ok": ok,
                "version": str(version),
                "error": error,
            },
        )
    return status


def print_status() -> int:
    failed = False
    print("Boltz protein-prep worker component check")
    for item in component_status():
        state = "ok" if item["ok"] else "missing"
        print(f"- {item['name']}: {state} {item['version']}")
        if item["error"]:
            print(f"  error: {item['error']}")
        if item["required"] and not item["ok"]:
            failed = True
    return 1 if failed else 0


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

    platform = os.getenv("BOLTZ_PREP_WORKER_PLATFORM", "unknown")
    poll_seconds = float(os.getenv("BOLTZ_PREP_POLL_SECONDS", "5"))
    print(f"protein-prep worker ready; platform={platform}; poll_seconds={poll_seconds}", flush=True)
    print("queue execution is reserved for the next integration slice; this process keeps the worker container healthy", flush=True)

    while not exit_requested:
        time.sleep(poll_seconds)
    print("protein-prep worker stopped", flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Boltz protein-preparation worker")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="check required preparation components and exit")
    group.add_argument("--watch", action="store_true", help="start the worker placeholder loop")
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
