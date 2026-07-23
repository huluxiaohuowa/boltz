# Boltz VOS App Packaging

This directory contains the initial VOS app definition scaffold for
`com.ictrek.boltz`.

The current package is a webapp-oriented template. It provides manifest,
configuration, router, compose, and release-version scaffolding before the
Boltz-specific web service and frontend are implemented.

## Package

```bash
cd apps/boltz/ictrek.app
BOLTZ_WEB_IMAGE=<registry>/<image>:<tag> ./scripts/package.sh
```

The script creates one pull-mode package:

```text
dist/boltz_${VERSION}_pull.tar
```

The package contains `app.tar.gz` only. It does not embed Docker image archives
or model weights.

## Runtime Contract

The placeholder compose template exposes one web service:

- VOS entry: `/app/com.ictrek.boltz/`
- container port: `8080`
- shared data path: `${BOLTZ_DATA_PATH:-/data/vos_workspace/boltz}`
- optional Model Hub cache path:
  `${MODEL_HUB_SHARED_MODELS_PATH:-/data/vos_workspace/model_hub}`

When the real webapp is added, keep the VOS route stable unless there is a
compatibility reason to change it.

