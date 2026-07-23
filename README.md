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

VOS packaging is intentionally not part of this development path yet.

Default login:

- username: `admin`
- password: `admin123456`

New users can submit registration requests from the login screen. Admin approval
is required before they can use the workbench. The backend also exposes a
`BOLTZ_USER_PROVISION_TOKEN` protected endpoint for later VOS account
provisioning.

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
