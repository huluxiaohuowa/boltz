# Boltz WebApp

This repository is the ictrek fork of Boltz for building a VOS web application
around biomolecular structure and affinity prediction.

The upstream Boltz project README is preserved in [README.origin.md](README.origin.md).
Keep upstream documentation changes there when merging from
`git@github.com:jwohlwend/boltz.git`.

## Development Scope

The webapp will wrap Boltz prediction workflows with a browser-based interface
for preparing inputs, submitting jobs, tracking progress, and collecting
prediction outputs.

Initial application goals:

- provide a VOS iframe entry for Boltz jobs;
- keep original Boltz CLI/library code available for reuse;
- add webapp-specific services and UI without rewriting upstream model code;
- package the app through `ictrek.app/` for VOS installation.

## Repository Layout

```text
.
├── README.md              # ictrek webapp development entry
├── README.origin.md       # upstream Boltz README
├── ictrek.app/            # VOS app package templates and scripts
├── src/                   # upstream Boltz Python package
├── docs/                  # upstream Boltz docs
├── examples/              # upstream Boltz examples
└── tests/                 # upstream Boltz tests
```

## Remotes

```bash
git remote -v
```

Expected remotes:

- `origin`: `git@github.com:huluxiaohuowa/boltz.git`
- `upstream`: `git@github.com:jwohlwend/boltz.git`

Use `upstream` only as a read-only reference for merging original Boltz code.
Push ictrek webapp work to `origin`.

## Independent WebApp

Install the Boltz package in a Python environment when working on prediction
integration:

```bash
pip install -e ".[cuda]"
```

Run Boltz directly while the webapp layer is still being built:

```bash
boltz predict input.yaml --use_msa_server
```

Webapp service and frontend commands will be added once the application runtime
is introduced. The initial WebServer is now available as a FastAPI app:

```bash
export BOLTZ_DATABASE_URL=postgresql+psycopg://boltz:boltz@127.0.0.1:5432/boltz
export BOLTZ_REDIS_URL=redis://127.0.0.1:6379/0
export BOLTZ_DATA_DIR=/tmp/boltz-web-data
boltz-web
```

The first development slice is documented in
[docs/ictrek-webserver.md](docs/ictrek-webserver.md).

For a standalone container stack, use the dedicated compose file:

```bash
cp .env.web.example .env.web
# Edit PGV_POSTGRES_IMAGE to the PGV postgres image tag you want to use.
docker compose --env-file .env.web -f docker-compose.web.yml up --build
```

The stack starts:

- `boltz-web`: FastAPI WebServer and static workbench.
- `boltz-postgres`: Postgres using the PGV image from `PGV_POSTGRES_IMAGE`.
- `boltz-redis`: Redis for task event streams and status cache.

BOLTZ user/project/asset files are stored under `BOLTZ_DATA_HOST_DIR` on the
host and mounted into the web container at `/data`. Set this to a persistent
SSD path in production, for example:

```bash
BOLTZ_DATA_HOST_DIR=/data/ssd/jhu/boltz-web/data
```

VOS packaging is intentionally not part of this development path yet.

Default login:

- username: `admin`
- password: `admin123456`

New users can submit registration requests from the login screen. Admin approval
is required before they can use the workbench. The backend also exposes a
`BOLTZ_USER_PROVISION_TOKEN` protected endpoint for later VOS account
provisioning.

The standalone workbench is organized by workflow module:

- Project: current project, reusable assets, and recent tasks.
- Protein: left-side PDB/upload/asset/preparation controls and a wide right-side
  3Dmol protein workspace. Selecting a protein asset loads its PDB file through
  the authenticated asset download API and enables Cartoon, Surface, Pocket,
  Ligand, Waters, Metals, H-bonds, and Clashes display toggles. The workspace
  parses PDB `HETATM` records into candidate ligands, metals, and water records.
  A candidate ligand can be used as a pocket reference; the UI computes the
  pocket center and box size, writes those values into protein preparation and
  docking fields, and can persist them as a `pocket` asset. The first CADD
  preparation form records water removal, metal/cofactor retention,
  hydrogen/protonation settings, missing atom repair, alternate-location
  handling, pH, and pocket definition, then creates a `prepared_protein` asset
  that later workers can consume.
- Ligand: left-side SMILES/upload/asset controls and a wide right-side ligand
  preview/editing workspace.
- Docking: left-side protein/ligand/pocket/task controls and a wide right-side
  3D docking workspace for pocket, pose, interaction, and score inspection.
- FEP / Analysis: left-side input/settings controls and a wide right-side
  analysis workspace reserved for FEP and downstream reports.
- SAR / Structure-activity relationship: left-side data-mapping controls and a
  wide right-side compound-series workspace reserved for compound-series
  decision analysis using ligand assets, activity tables, docking results, FEP
  results, and ADMET fields.
- Admin: user approval and future service/worker status, visible to admins.

Terminology used by the workbench:

- User: login account and isolation boundary.
- Project: a user-owned workspace for one target, study, or compound series.
- Asset: reusable data object inside a project, such as a protein, ligand,
  complex, docking result, FEP result, or SAR analysis.
- Task: computation over one or more assets. Task outputs should become new
  assets so later tasks can reuse them.
- File: concrete stored file under an asset or task output, such as PDB, SDF,
  CSV, logs, or reports.

## VOS Packaging

The VOS package scaffold lives in `ictrek.app/`, but VOS integration is deferred.

```bash
cd ictrek.app
./scripts/package.sh
```

The current template expects a prebuilt web image supplied through
`BOLTZ_WEB_IMAGE`. Later releases can replace it with CI-populated image
values.

```bash
docker build -f Dockerfile.web -t boltz-web:dev .
```
