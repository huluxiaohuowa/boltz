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

## Build acceleration mirrors

The worker Dockerfiles expose mirror build arguments, so a deployment host can
switch between Tencent Cloud, USTC, Tsinghua, or an internal mirror without
changing source code:

```bash
# Tsinghua/TUNA, current default for protein-prep images
CONDA_FORGE_CHANNEL=https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge \
MINIFORGE_BASE_URL=https://mirrors.tuna.tsinghua.edu.cn/github-release/conda-forge/miniforge/LatestRelease \
./build_image.sh --component protein-prep-arm --tag arm_YYYYMMDD

# USTC conda-forge channel
CONDA_FORGE_CHANNEL=https://mirrors.ustc.edu.cn/anaconda/cloud/conda-forge \
./build_image.sh --component protein-prep-amd --tag amd_YYYYMMDD

# Tencent Cloud conda-forge channel
CONDA_FORGE_CHANNEL=https://mirrors.cloud.tencent.com/anaconda/cloud/conda-forge \
./build_image.sh --component protein-prep-arm --tag arm_YYYYMMDD
```

`APT_MIRROR`, `APT_SECURITY_MIRROR`, `MINIFORGE_BASE_URL`, and
`CONDA_FORGE_CHANNEL` are all ordinary build args/env overrides. The current
protein-prep defaults use HTTP for Debian apt because `debian:bookworm-slim`
does not include CA certificates before the first `apt-get install`.

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

## ARM worker

The protein-preparation worker is CPU-oriented. It does not need GPU, PyTorch,
CUDA, or a JetPack-specific base image. On ARM/aarch64 hosts, build and tag it
with an `arm_YYYYMMDD` tag; override the base image only when the deployment
uses an internal ARM CPU base:

```bash
export PROTEIN_PREP_ARM_BASE_IMAGE=<arm64-cpu-base-image>
docker compose --env-file .env.web \
  -f docker-compose.web.yml \
  -f docker-compose.protein-prep.arm.yml \
  --profile protein-prep up --build -d boltz-protein-prep-worker
```

Use `amd_YYYYMMDD` for x86_64 builds and `arm_YYYYMMDD` for aarch64 builds.
Reserve `thor_YYYYMMDD` tags for images that actually depend on Thor-specific
GPU/CUDA/JetPack runtime behavior, such as future Boltz model inference images.

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
