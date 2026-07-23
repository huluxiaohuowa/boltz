# Boltz WebServer Design

This document records the first WebServer slice for the ictrek Boltz WebApp.

## Modules

- Molecular assets: user-scoped proteins, ligands, complexes, prepared assets,
  and result assets.
- Projects: user-scoped workspaces that separate assets, jobs, and files.
- Preparation pipeline: placeholder protein and ligand preparation operations
  that create derived assets without mutating source files.
- File storage: immutable input and output files under
  `BOLTZ_DATA_DIR/users/<user>/`.
- Jobs: user-scoped task records whose output assets can be reused as input by
  later jobs.
- Runtime state: Postgres is the source of record; Redis stores short job event
  streams and publishes updates.

## Current API Surface

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/register`
- `GET /api/v1/admin/users`
- `POST /api/v1/admin/users/{username}/approve`
- `POST /api/v1/auth/provision-vos-user`
- `POST /api/v1/projects`
- `GET /api/v1/projects`
- `POST /api/v1/assets/proteins/pdb`
- `POST /api/v1/assets/upload`
- `POST /api/v1/assets/ligands/smiles`
- `POST /api/v1/assets/ligands/table`
- `POST /api/v1/assets/ligands/draw`
- `GET /api/v1/assets`
- `GET /api/v1/assets/{asset_id}`
- `GET /api/v1/assets/{asset_id}/files/{file_id}/download`
- `POST /api/v1/preparations/protein`
- `POST /api/v1/preparations/ligand`
- `POST /api/v1/jobs`
- `GET /api/v1/jobs`
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/jobs/{job_id}/events`

## User Isolation

The first slice uses built-in login and Bearer tokens. It creates an initial
admin account on startup:

- username: `admin`
- password: `admin123456`

All project, asset, file, and job queries are scoped by the authenticated user
id. Assets and jobs additionally carry `project_id`, so one account can keep
separate CADD studies isolated from each other.

Files are stored under:

```text
BOLTZ_DATA_DIR/users/<user>/projects/<project_id>/
├── assets/<asset_id>/
└── jobs/<job_id>/
```

Database records carry the same `user_id` and `project_id`. If no project is
provided, the backend creates or reuses a per-user `default` project.

Self-registration creates users with `pending` status. Admin users must approve
them through `POST /api/v1/admin/users/{username}/approve` before they can log
in.

For later VOS identity integration, `POST /api/v1/auth/provision-vos-user`
creates or activates a user directly. It is protected by
`BOLTZ_USER_PROVISION_TOKEN` and should be called only by a trusted VOS-side
adapter.

## Preparation Status

Ligand SMILES and drawn ligand inputs already use RDKit to generate SDF files.
Protein and ligand preparation endpoints currently create versioned derived
assets and metadata placeholders. The actual CADD preparation adapters should
be added behind these endpoints.

## Viewer Status

The static workbench page is a placeholder for the commercial-grade viewer. It
keeps the route and API integration stable while Mol* editing, pocket display,
and interaction rendering are added.
