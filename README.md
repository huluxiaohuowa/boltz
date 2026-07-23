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

## Local Development

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
is introduced.

## VOS Packaging

The VOS package scaffold lives in `ictrek.app/`.

```bash
cd ictrek.app
./scripts/package.sh
```

The current template expects a prebuilt web image supplied through
`BOLTZ_WEB_IMAGE`. Later releases can replace this with CI-populated image
values.

