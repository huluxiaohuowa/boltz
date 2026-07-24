# 配体处理 / Ligand Preparation

## 作用 / Role

配体处理用于创建、上传、编辑、扩充和准备小分子库，并生成 Boltz 可用的 ligand 输入。

Ligand preparation creates, uploads, edits, extends, and prepares ligand libraries for Boltz-ready inputs.

## 输入 / Inputs

- 空白配体库 / empty ligand library
- SMILES 列表 / SMILES list
- SDF 上传 / SDF upload
- Ketcher 绘制或 MolBlock / Ketcher drawing or MolBlock

## 输出 / Outputs

- `ligand` asset
- `prepared_ligand` asset
- `boltz_prediction_input` asset containing `input.yaml`

## 执行引擎 / Execution Engine

生产部署应启用 `boltz-ligand-prep-worker`。该 worker 是 CPU 镜像，不需要 GPU 或 PyTorch，包含 RDKit、OpenBabel、Meeko 和 Dimorphite-DL。当前已执行的准备步骤包括盐拆分、中和、3D 构象生成、MMFF/UFF 优化、tautomer 枚举和 stereoisomer 枚举。

Production deployments should enable `boltz-ligand-prep-worker`. This CPU worker does not require GPU or PyTorch and bundles RDKit, OpenBabel, Meeko, and Dimorphite-DL. The current execution path covers salt stripping, neutralization, 3D conformer generation, MMFF/UFF optimization, tautomer enumeration, and stereoisomer enumeration.

如果 worker 已启用，`POST /api/v1/preparations/ligand` 会返回一个 `prepared_ligand` 资产和对应 `job_id`，任务状态从 `queued` 进入 `running/completed/failed`。网页任务列表和 API events 都能跟踪进度。

When the worker is enabled, `POST /api/v1/preparations/ligand` returns a `prepared_ligand` asset and its `job_id`; job state moves from `queued` to `running/completed/failed`. The web job list and job events API expose progress.

## API / Automation

```http
POST /api/v1/assets/ligands/empty
POST /api/v1/assets/ligands/smiles
POST /api/v1/assets/upload
POST /api/v1/assets/ligands/{asset_id}/molecules
PUT /api/v1/assets/ligands/{asset_id}/molecules/{index}
POST /api/v1/preparations/ligand
POST /api/v1/boltz-inputs
```

自动化衔接：先得到 ligand `asset_id`，准备后得到 `prepared_ligand.asset_id`，再与 `prepared_protein.asset_id`、`pocket.asset_id` 一起生成 Boltz input。
