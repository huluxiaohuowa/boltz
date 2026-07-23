# Protein Preparation Worker

The FastAPI web container is not the chemistry execution environment. It stores
users, projects, files, task parameters, and reusable assets. Protein cleanup,
repair, protonation, and pocket materialization should run in a separate
protein-preparation worker image.

## Component choices

The worker image installs the preparation stack through conda-forge:

- Gemmi: high-performance PDB/mmCIF parsing, component selection, and structure
  writing. Gemmi is a C++ library with Python bindings and normally installs
  from wheels or conda packages; no source submodule is needed here.
- PDBFixer/OpenMM: missing atom/residue repair and structure normalization.
- PropKa/PDB2PQR/Reduce-compatible workflow: pH-aware protonation and hydrogen
  placement. The first image includes PropKa and PDB2PQR; Reduce can be added
  through a later worker image variant if the deployment standard requires it.
- RDKit: ligand/cofactor chemistry checks.
- MDAnalysis/NumPy/SciPy: selections, neighborhoods, and pocket geometry.
- Redis/SQLAlchemy/psycopg: later queue/database integration with the web app.

## AMD worker

Use this overlay together with the web compose file:

```bash
docker compose --env-file .env.web \
  -f docker-compose.web.yml \
  -f docker-compose.protein-prep.amd.yml \
  --profile protein-prep up --build -d boltz-protein-prep-worker
```

The default AMD base is `debian:bookworm-slim`; override it with
`PROTEIN_PREP_AMD_BASE_IMAGE` when a site requires an internal base image.

## Thor worker

Thor deployments must use a base image that matches the installed
JetPack/L4T/CUDA runtime. Set `PROTEIN_PREP_THOR_BASE_IMAGE` before building:

```bash
export PROTEIN_PREP_THOR_BASE_IMAGE=<thor-l4t-cuda-base-image>
docker compose --env-file .env.web \
  -f docker-compose.web.yml \
  -f docker-compose.protein-prep.thor.yml \
  --profile protein-prep up --build -d boltz-protein-prep-worker
```

The Thor compose overlay enables GPU visibility for future OpenMM CUDA-backed
steps. Most protein preparation work is CPU-bound, but keeping the worker
CUDA-aware avoids redesigning the service when GPU-backed minimization or
validation is added.

## Current worker behavior

The current worker image provides a component check and a placeholder health
loop:

```bash
python -m boltz_prep.worker --check
python -m boltz_prep.worker --watch
```

Queue execution is intentionally left for the next integration slice, where
`preparation` jobs from Postgres/Redis will be consumed and converted into
`prepared_protein` output assets.
