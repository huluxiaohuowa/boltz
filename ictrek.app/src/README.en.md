# Boltz

The Boltz VOS app hosts biomolecular structure prediction and protein-ligand
affinity prediction workflows.

This version is a WebApp development scaffold. It provides the VOS app entry,
configuration, router, and Compose skeleton. Job submission, input preparation,
result management, and inference scheduling will be implemented later.

## Entry

After installation, open Boltz from the VOS sidebar. The app entry is:

```text
/app/com.ictrek.boltz/
```

## Configuration

- `BOLTZ_DATA_PATH`: directory for job inputs, outputs, and cache files.
- `MODEL_HUB_SHARED_MODELS_PATH`: optional Model Hub shared model directory.
- `BOLTZ_WEB_HOST_PORT`: optional host port for exposing the web service.

