# Boltz WebApp

Boltz WebApp is an ictrek fork of Boltz that adds a browser workbench for CADD
input preparation, molecular inspection, task tracking, and Boltz-ready asset
management.

Boltz WebApp 是 Boltz 的 ictrek 工作分支，目标是在浏览器里完成 CADD 输入准备、分子结构检查、任务跟踪和 Boltz 可复用资产管理。

![Boltz Workbench main page](docs/images/boltz-workbench-main.png)

## 功能分类 / Feature Categories

| 模块 | 中文说明 | English |
| --- | --- | --- |
| 项目与资产 / Projects & Assets | 用户隔离的项目、输入/输出文件、跨项目复制、下载、重命名、删除。 | User-isolated projects, reusable input/output assets, cross-project copy, download, rename, and deletion. |
| 蛋白处理 / Protein Preparation | PDB ID 导入、本地上传、3D 预览、链/组分/配体/金属/水对象管理、口袋定义、准备后蛋白资产输出。 | PDB import, local upload, 3D inspection, chain/component/ligand/metal/water management, pocket definition, and prepared-protein outputs. |
| 配体处理 / Ligand Preparation | 空白配体库、SMILES/SDF 导入、Ketcher 2D 编辑、库内追加/替换、RDKit CPU 准备、Boltz input.yaml 生成。 | Empty ligand libraries, SMILES/SDF import, Ketcher 2D editing, append/replace molecules, CPU RDKit preparation, and Boltz input.yaml generation. |
| 对接任务 / Docking Tasks | 组合 prepared protein、ligand 和 pocket，生成任务记录与可复用输出。 | Combine prepared proteins, ligands, and pockets into tracked docking or prediction tasks. |
| 分子生成 / Molecule Generation | 预留基于 pocket asset 的 3D 分子生成入口。 | Planned pocket-conditioned 3D molecule generation entry. |
| TPD / PROTAC | 预留 POI/E3/warhead/linker 的 Targeted Protein Degradation 工作流。 | Planned Targeted Protein Degradation workflow for POI, E3, warheads, and linkers. |
| FEP / 分析 | 预留自由能计算、轨迹、误差和报告入口。 | Planned FEP, trajectory, uncertainty, and report workflow. |
| SAR / 构效关系 | 预留活性表、R-group、MMPA 和下一轮设计入口。 | Planned activity table, R-group, MMPA, and next-design workflow. |
| 管理 / Admin | 用户审核、全局任务停止/清理/删除、用户级联删除、部署机器资源监控。 | User approval, global task cancel/cleanup/delete, cascading user deletion, and host resource monitoring. |
| API 文档 / API Docs | 页面内从 OpenAPI 自动生成接口目录，并提供 asset_id/job_id 自动化衔接示例。 | In-app API catalog generated from OpenAPI with asset_id/job_id chaining examples. |

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

Build and push production images from the target build host with:

```bash
./build_image.sh --component web --tag arm_YYYYMMDD
```

The script uses the same repository-plus-tag convention as the other ictrek app
image build scripts:

```text
swr.cn-east-3.myhuaweicloud.com/huluxiaohuowa/boltz-web:arm_YYYYMMDD
```

Protein-preparation worker images are separate from the web image. This worker
is CPU-oriented and does not need PyTorch or CUDA; override the base image only
when a site requires an internal AMD/ARM CPU base:

```bash
PROTEIN_PREP_ARM_BASE_IMAGE=<arm64-cpu-base-image> \
  ./build_image.sh --component protein-prep-arm --tag arm_YYYYMMDD
```

Ligand preparation also has a separate CPU worker image. It is the production
path for CADD ligand preparation and includes RDKit, OpenBabel, Meeko, and
Dimorphite-DL. The web image keeps only the UI/API orchestration and lightweight
fallback logic:

```bash
LIGAND_PREP_ARM_BASE_IMAGE=<arm64-cpu-base-image> \
  ./build_image.sh --component ligand-prep-arm --tag arm_YYYYMMDD
```

The worker Dockerfiles expose mirror overrides for reproducible builds in
domestic networks:

```bash
# Tsinghua/TUNA, current default
CONDA_FORGE_CHANNEL=https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge \
MINIFORGE_BASE_URL=https://mirrors.tuna.tsinghua.edu.cn/github-release/conda-forge/miniforge/LatestRelease \
./build_image.sh --component protein-prep-arm --tag arm_YYYYMMDD

# USTC or Tencent Cloud conda-forge can also be used
CONDA_FORGE_CHANNEL=https://mirrors.ustc.edu.cn/anaconda/cloud/conda-forge \
./build_image.sh --component protein-prep-amd --tag amd_YYYYMMDD

CONDA_FORGE_CHANNEL=https://mirrors.cloud.tencent.com/anaconda/cloud/conda-forge \
./build_image.sh --component protein-prep-arm --tag arm_YYYYMMDD
```

`APT_MIRROR`, `APT_SECURITY_MIRROR`, `MINIFORGE_BASE_URL`, and
`CONDA_FORGE_CHANNEL` can all be overridden from the build environment. Keep
CPU-only images tagged as `amd_YYYYMMDD` or `arm_YYYYMMDD`; reserve
`thor_YYYYMMDD` for future GPU/CUDA runtime images.

The stack starts:

- `boltz-web`: FastAPI WebServer and static workbench.
- `boltz-ligand-prep-worker`: CPU ligand preparation worker with RDKit,
  OpenBabel, Meeko, and Dimorphite-DL.
- `boltz-protein-prep-worker`: CPU protein preparation worker image scaffold.
- `boltz-postgres`: Postgres using the PGV image from `PGV_POSTGRES_IMAGE`.
- `boltz-redis`: Redis for task event streams and status cache.

Optional preparation workers are provided as compose overlays:

```bash
# AMD/x86_64 CPU workers
docker compose --env-file .env.web \
  -f docker-compose.web.yml \
  -f docker-compose.protein-prep.amd.yml \
  -f docker-compose.ligand-prep.amd.yml \
  --profile protein-prep up --build -d boltz-protein-prep-worker
docker compose --env-file .env.web \
  -f docker-compose.web.yml \
  -f docker-compose.ligand-prep.amd.yml \
  --profile ligand-prep up --build -d boltz-ligand-prep-worker

# ARM/aarch64 CPU workers; override only if the deployment uses an internal base.
export PROTEIN_PREP_ARM_BASE_IMAGE=<arm64-cpu-base-image>
export LIGAND_PREP_ARM_BASE_IMAGE=<arm64-cpu-base-image>
docker compose --env-file .env.web \
  -f docker-compose.web.yml \
  -f docker-compose.protein-prep.arm.yml \
  -f docker-compose.ligand-prep.arm.yml \
  --profile protein-prep up --build -d boltz-protein-prep-worker
docker compose --env-file .env.web \
  -f docker-compose.web.yml \
  -f docker-compose.ligand-prep.arm.yml \
  --profile ligand-prep up --build -d boltz-ligand-prep-worker
```

See [docs/protein-prep-worker.md](docs/protein-prep-worker.md) for the worker
component stack and platform notes.

BOLTZ user/project/asset files and model cache are stored under
`BOLTZ_DATA_HOST_DIR` on the host and mounted into the web container at `/data`.
Set this to a persistent SSD path in production, for example:

```bash
BOLTZ_DATA_HOST_DIR=/data/ssd/jhu/boltz-web/data
```

The compose file sets `BOLTZ_CACHE=/data/model-cache`, so Boltz model downloads
also persist under the same host directory:

```text
/data/ssd/jhu/boltz-web/data/model-cache
```

Use the ModelScope mirror for Boltz-2 model files instead of re-downloading from
the original source:

```bash
pip install modelscope
modelscope download \
  --model huluxiaohuowa/boltz-2-mirror \
  --local_dir /data/ssd/jhu/boltz-web/data/model-cache
```

Expected mirrored files include `boltz2_conf.ckpt`, `boltz2_aff.ckpt`, and
`mols.tar`. Keep them in the persistent cache directory so restarting or
rebuilding the web/model containers does not lose the model.

VOS packaging is intentionally not part of this development path yet.

Default login:

- username: `admin`
- password: `admin123456`

New users can submit registration requests from the login screen. Admin approval
is required before they can use the workbench. The backend also exposes a
`BOLTZ_USER_PROVISION_TOKEN` protected endpoint for later VOS account
provisioning.

## User Guides / 使用指南

Each workflow module has a bilingual guide under [userguide](userguide):

- [Project and assets / 项目与资产](userguide/project-and-assets.md)
- [Protein preparation / 蛋白处理](userguide/protein-preparation.md)
- [Ligand preparation / 配体处理](userguide/ligand-preparation.md)
- [Docking tasks / 对接任务](userguide/docking-tasks.md)
- [Molecule generation / 分子生成](userguide/molecule-generation.md)
- [TPD / PROTAC](userguide/tpd-protac.md)
- [FEP and analysis / FEP 与分析](userguide/fep-analysis.md)
- [SAR / 构效关系](userguide/sar.md)
- [Admin / 管理](userguide/admin.md)
- [API automation / API 自动化](userguide/api-automation.md)

The standalone workbench is organized by workflow module:

- Project: current project, reusable assets, and recent tasks.
- Protein: left-side PDB/upload/asset/preparation controls and a wide right-side
  3Dmol protein workspace. Selecting a protein asset loads its PDB file through
  the authenticated asset download API and enables Cartoon, Surface, Pocket,
  Ligand, Waters, Metals, H-bonds, and Clashes display toggles. The workspace
  parses PDB `HETATM` records into candidate ligands, metals, and water records.
  The 3D workspace supports CADD-style selection modes for atom, residue, chain,
  HETATM component, and pocket picking. Component mode is the default for
  docking preparation: clicking a ligand selects the full molecule and enters
  ligand editing instead of changing one atom into a separate object. Atom mode
  highlights only one atom for inspection, residue mode highlights one residue,
  chain mode highlights a whole chain, and pocket mode creates pocket parameters
  from a clicked ligand or residue center. Defined pockets are shown in the 3D
  viewer as a blue center marker and box guide. The right rail shows the pocket
  reference, center, and box size, and allows manual adjustment of center and
  box dimensions with live 3D guide updates while typing. The protein workspace
  also has a true focus editor mode that covers the full browser window, hides
  the page chrome and left-side forms, keeps the 3D viewer wide, leaves
  display/edit actions in a fixed right rail, and exposes both a right-rail
  exit button and a fixed top-left return button.
  In focus mode, a bottom horizontal object strip lists the parsed PDB objects:
  protein chains, ligands, cofactors, metals, and waters. Object cards can be
  focused, downloaded as individual PDB fragments, marked for deletion or
  restored; ligand cards can also define the docking pocket. The same chain and
  HETATM component operations are available in the normal protein page cards.
  A selected ligand can be focused, hidden or restored, and used as a pocket
  reference. The UI computes the pocket center and box size, writes those values
  into protein preparation and docking fields, and can persist them as a
  `pocket` asset. The first CADD preparation form records output asset naming,
  batch naming pattern, chain/component delete lists, water removal,
  metal/cofactor retention, hydrogen/protonation settings, missing atom repair,
  alternate-location handling, pH, and pocket definition, then creates a
  `prepared_protein` asset that later workers can consume.
- Ligand: left-side SMILES/upload/asset controls and a wide right-side ligand
  preview/editing workspace. The first Boltz-first ligand-preparation slice
  parses SDF/SMILES assets into molecule rows, lets one molecule be selected for
  Boltz chain-id assignment, supports editing a selected molecule through the
  bundled Ketcher 2D molecule editor, synchronizes Ketcher output back to
  SMILES/MolBlock, saves the edited molecule as a new ligand asset, and can
  generate a `boltz_prediction_input` asset containing `input.yaml` plus
  `report.json`. Ketcher is bundled into the `boltz-web` image at build time;
  the runtime does not load editor code from a CDN.
  PDBQT remains an optional future AutoDock/Vina export rather than the default
  ligand output.
- Docking: left-side protein/ligand/pocket/task controls and a wide right-side
  3D docking workspace for pocket, pose, interaction, and score inspection.
- FEP / Analysis: left-side input/settings controls and a wide right-side
  analysis workspace reserved for FEP and downstream reports.
- SAR / Structure-activity relationship: left-side data-mapping controls and a
  wide right-side compound-series workspace reserved for compound-series
  decision analysis using ligand assets, activity tables, docking results, FEP
  results, and ADMET fields.
- Admin: user approval and future service/worker status, visible to admins.

The standalone workbench uses hash routes for workflow modules so browser
refresh keeps the current module without requiring backend SPA fallback routes:

- `/#/project`
- `/#/protein`
- `/#/ligand`
- `/#/docking`
- `/#/fep`
- `/#/sar`
- `/#/admin`

The browser also stores the current project, selected protein, selected ligand,
and temporary pocket parameters in local storage so a refresh can restore the
active workbench context.

Protein preparation execution is intentionally separated from the FastAPI web
image. The web image stores user intent and creates traceable assets; production
chemistry work should run in a dedicated protein-preparation worker image. The
recommended worker stack is:

- Gemmi for high-performance PDB/mmCIF parsing, chain/residue/component
  selection, and structure writing. Most Linux x86_64/aarch64 deployments can
  install it from Python wheels with `pip install gemmi`; only unsupported
  architectures need a C++/CMake build stage.
- PDBFixer/OpenMM for missing atom/residue repair and structure normalization.
- PropKa/PDB2PQR/Reduce for pH-aware protonation and hydrogen placement.
- Gemmi/MDAnalysis/NumPy for water/metal/cofactor retention rules, pocket
  neighborhoods, and prepared output asset generation.

Terminology used by the workbench:

- User: login account and isolation boundary.
- Project: a user-owned workspace for one target, study, or compound series.
- Asset: reusable data object inside a project, such as a protein, ligand,
  complex, docking result, FEP result, or SAR analysis.
- Task: computation over one or more assets. Task outputs should become new
  assets so later tasks can reuse them.
- File: concrete stored file under an asset or task output, such as PDB, SDF,
  CSV, logs, or reports.

The workbench now treats protein preparation as a traceable task rather than a
silent file copy:

- Clicking protein preparation creates a `preparation` task, emits Redis-backed
  progress events, runs the current text-level PDB cleanup executor, and writes
  a `prepared_protein` output asset.
- The built-in executor supports chain deletion, HETATM component deletion, and
  water removal. It records add-hydrogen, protonation, missing-atom repair, and
  alternate-location cleanup requests as unsupported worker operations instead
  of pretending chemistry preparation has been completed.
- Task cards show status, input assets, output assets, output filenames,
  cleanup statistics, and progress events. The browser polls the current project
  task list while the user is logged in.
- Failed preparation tasks can be retried from the task card. Tasks with output
  assets can delete generated intermediate/output assets and files while keeping
  the task record.
- Output assets can be previewed, renamed, downloaded, deleted, used by later
  workflow modules, or copied into another project with a new name.

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

For sites that cannot reliably pull Docker Hub base images, set
`WEB_BASE_IMAGE` in `.env.web` to an internal mirror or a locally preloaded
Python/web base image. The tc81 deployment currently builds from a local
`boltz-web:base` image to avoid repeated external base-image pulls.
