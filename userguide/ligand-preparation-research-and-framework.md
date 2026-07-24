# 配体准备功能清单与开发框架 / Ligand Preparation Requirements and Development Framework

本文面向 Boltz Workbench 的配体准备模块，目标是满足 CADD 研究人员在分子对接、Boltz 任务、虚拟筛选、SAR/FEP 后续分析中的常见配体准备需求。

This document defines the ligand-preparation capability required by Boltz Workbench for CADD workflows: docking, Boltz prediction, virtual screening, SAR, and FEP. The implementation should not be a thin web-only SMILES converter. The production path uses a dedicated ligand-prep worker so that chemistry dependencies, future commercial tool adapters, and compute isolation can be managed independently from the web server.

## English executive summary

The ligand workflow must be Boltz-first. For Boltz, the primary ligand input is a `ligand` entry with `smiles` or `ccd`; SDF and MOL2 are useful audit/interchange formats, while PDBQT is only a compatibility output for AutoDock/Vina. The web application should manage upload, table mapping, Ketcher editing, asset lineage, Boltz YAML preview, job submission, and file management. The `boltz-ligand-prep-worker` should run the chemistry pipeline.

Minimum production capabilities:

- Inputs: SMILES lists, SDF/MOL/MOL2/PDB upload, tabular files with a SMILES column, empty ligand libraries, and Ketcher drawing/editing.
- Editing: edit a single molecule from an uploaded file or molecule library; save as a new asset/version by default; keep source asset, row index, molecule name, and edit reason.
- Standardization: RDKit sanitize, salt stripping, largest-fragment selection, metal disconnection, neutralization/reionization, canonical SMILES, InChIKey deduplication, and failed-molecule reports.
- Enumeration: pH-aware protonation when the backend is available, tautomer enumeration, undefined stereocenter enumeration, E/Z enumeration, and per-input variant limits.
- 3D preparation: conformer generation, MMFF/UFF optimization, conformer pruning, failure reporting, and optional retention of supplied 3D coordinates.
- Boltz output: stable ligand chain IDs, prepared SMILES or CCD, affinity binder configuration, pocket constraint linkage, YAML preview, and batch YAML export.
- Optional compatibility: SDF/MOL2 for exchange, Meeko PDBQT for AutoDock/Vina, Open Babel fallback conversion.

Current implementation direction:

```text
WebApp / FastAPI
  -> uploads, Ketcher, tables, assets, API docs, task orchestration
boltz-ligand-prep-worker
  -> RDKit + OpenBabel + Meeko + Dimorphite-DL chemistry execution
assets
  -> ligand, prepared_ligand, boltz_prediction_input, optional docking_ready_ligand
```

## 1. 结论

第一版必须以 Boltz 为主线，而不是以 AutoDock/Vina 为主线。Boltz 的配体输入核心是 `ligand` 条目里的 `smiles` 或 `ccd`，亲和力预测还需要明确 `properties.affinity.binder` 对应哪个 ligand chain id。PDBQT 只是给 AutoDock/Vina 的可选兼容导出，不应成为默认产物。

建议采用：

```text
WebApp / FastAPI
  负责：上传、表格列映射、分子编辑、Boltz chain_id 设置、
       YAML 预览、任务提交、任务状态、资产/文件管理

ligand-prep-worker
  负责：RDKit 主流程 + Boltz-ready SMILES/CCD/YAML 生成
       + 可选 Meeko PDBQT / Open Babel fallback

输出资产
  prepared_ligand / prepared_ligand_library / boltz_ligand_input /
  boltz_prediction_input / ligand_conformer_set / optional docking_ready_ligand
```

不要把重计算和复杂化学处理都塞进 WebServer 镜像。WebServer 应保持轻量；配体准备应走独立 worker，这样后续能按 CPU/GPU/商业软件 license 分开部署。

开源优先路线：

1. `RDKit` 作为核心化学对象、标准化、去盐、去重、SMILES/SDF 读写、stereo/conformer 的基础引擎。
2. Boltz YAML 生成器作为第一优先输出：生成 ligand chain、SMILES/CCD、pocket/contact/affinity binder 配置。
3. `Gypsum-DL` 或 `molscrub` 作为状态枚举参考实现或可选后端。
4. `Open Babel` 作为格式转换和 fallback 工具，但不要优先把 Open Babel Python API 深度嵌入主程序，GPL 传播问题需要单独评估。
5. `Meeko` 只作为 AutoDock Vina / AutoDock-GPU 的 PDBQT 可选准备器。
6. 商业适配层预留 `Schrödinger LigPrep/Epik` 和 `OpenEye OMEGA/QUACPAC`，但不作为默认依赖。

## 2. CADD 配体准备需要覆盖的功能

### 2.0 Boltz 优先兼容原则

Boltz 预测任务里，小分子的主输入不是 SDF、MOL2 或 PDBQT，而是：

```yaml
sequences:
  - ligand:
      id: B
      smiles: "..."
```

或：

```yaml
sequences:
  - ligand:
      id: B
      ccd: ATP
```

亲和力预测还需要：

```yaml
properties:
  - affinity:
      binder: B
```

因此配体准备模块的生产目标应是：

1. 从用户输入得到可信的 canonical / prepared SMILES 或 CCD。
2. 给每个 ligand 分配稳定 chain id。
3. 生成 Boltz 可直接运行的 YAML。
4. 对 affinity 任务做 Boltz 限制检查。
5. 保留 SDF 作为审计、预览、跨工具交换和后续 FEP/SAR 的结构资产。

PDBQT 只属于 AutoDock/Vina 路线，不能作为 Boltz 任务的主输出。

### 2.1 输入能力

必须支持：

- 单分子 `SDF/MOL/MOL2/PDB` 上传。
- 多分子 `SDF` 上传。
- `SMILES` 列表输入。
- `CSV/TSV/XLSX` 表格上传，并允许选择：
  - SMILES 列；
  - 分子名称列；
  - compound ID 列；
  - activity / batch / series 等保留字段。
- 手动画分子：
  - 输出 molblock；
  - 同步生成 canonical SMILES；
  - 支持保存为 ligand asset。
- 分子库内单分子编辑：
  - 上传多分子 SDF 或 SMILES 列表后，用户能在表格里选择任意单个分子；
  - 点击 `编辑` 后进入 2D 分子编辑器；
  - 保存时不覆盖原分子，默认生成新的 edited ligand asset 或新版本；
  - 保留 `source_asset_id`、`source_row_index`、`source_molecule_id`、`edit_parent_id`。

建议支持：

- PubChem CID / ChEMBL ID / vendor ID 导入。
- 从蛋白 PDB 里提取已结合配体，另存为 ligand asset。
- 从 prepared protein / docking result 中复制配体到配体准备页面。
- 从 Boltz 预测输入 YAML 反向加载 ligand SMILES/CCD。

### 2.1.1 分子编辑器要求

前端应内置 2D 分子编辑器，推荐 Ketcher。它要覆盖三种入口：

1. 空白画分子
   - 用户从零绘制；
   - 保存为新的 ligand asset；
   - 同时保存 molblock、canonical SMILES 和 2D 预览图。

2. 编辑上传的单个分子
   - 用户上传单分子 SDF/MOL 后，点击 `编辑`；
   - 编辑器加载该分子的 molblock；
   - 保存后生成 edited ligand asset。

3. 编辑分子库里的某一行
   - 用户上传多分子 SDF 或 SMILES 表格；
   - 分子表按行展示；
   - 任意一行都能点击 `编辑`；
   - 保存时生成新分子版本，并在 manifest 里记录来源。

编辑器保存行为必须满足：

- 默认不覆盖原始分子。
- 保存后的新分子要重新经过 RDKit sanitize。
- 如果结构不合法，前端给出错误，不创建资产。
- 保存后的新分子可直接生成 Boltz YAML。
- 保留编辑历史：
  - `source_asset_id`
  - `source_molecule_id`
  - `source_row_index`
  - `edit_parent_id`
  - `edit_reason` 或用户备注。

### 2.2 标准化与清洗

必须支持：

- 解析失败检测，并把失败分子写入 `failed.sdf/csv`。
- RDKit sanitize。
- 去盐 / 取最大有机片段。
- 金属断键 / metal disconnector。
- 规范化官能团表示。
- 电荷规范化 / uncharge / reionize。
- canonical SMILES / InChIKey 去重。
- 分子名、原始行号、输入文件名保留。

建议支持：

- 保留盐形式的选项。
- 保留原始分子和 prepared 分子的映射。
- 支持按 InChIKey first block 或 full InChIKey 去重。
- 反应性基团、PAINS、共价 warhead、金属有机物的规则标注，不强制删除。

### 2.3 状态枚举

必须支持：

- pH 范围设置，例如 `7.4 ± 1.0`。
- 质子化状态枚举。
- tautomer 枚举。
- 未定义手性中心枚举。
- 未定义 E/Z 双键枚举。
- 每个输入分子的最大变体数限制。
- 每个变体保留 genealogy / variant reason。

建议支持：

- 药化规则过滤不合理 tautomer。
- 对已定义手性默认不翻转。
- 用户可选择：
  - 严格保留输入 stereo；
  - 枚举未定义 stereo；
  - 枚举所有 stereo。
- 按 pH、tautomer、stereo 分层展示变体树。

### 2.4 3D 构象生成与优化

必须支持：

- 从 1D/2D 生成 3D。
- 多 conformer 生成。
- MMFF94 或 UFF 初步优化。
- conformer 去重。
- 最大 conformer 数限制。
- 失败分子单独输出。

建议支持：

- ring conformer 处理，尤其 6 元环 chair/boat。
- macrocycle 单独策略。
- 保留原有 3D 坐标的选项。
- 对接前只输出一个低能构象，虚拟筛选可输出多构象库。

### 2.5 Boltz 兼容输出

必须支持：

- Boltz ligand chain id 设置，例如 `B`、`L1`、`LIG001`。
- 每个 prepared ligand 输出 Boltz 可用 `smiles`。
- 如果用户选择 CCD 配体，输出 Boltz 可用 `ccd`，且不能同时写 `smiles`。
- 生成单配体 Boltz YAML。
- 生成批量 Boltz YAML 目录或打包文件。
- 生成 affinity 配置：
  - `properties.affinity.binder: <ligand_chain_id>`。
- 如果使用口袋约束，支持把项目里的 pocket asset 转成 Boltz `constraints.pocket`。
- 对 Boltz affinity 限制做前置检查：
  - 只能指定一个小分子 binder；
  - binder 必须是 ligand chain；
  - ligand 原子数超过官方建议阈值时 warning；
  - ligand 超过硬限制时阻止提交。

建议支持：

- 为每个 ligand 自动分配稳定 chain id。
- 让用户在 UI 中编辑 chain id。
- 显示 YAML 预览。
- 一键复制 YAML。
- 输出 `input.yaml`、`manifest.csv`、`report.json`。
- 支持一个蛋白 + 多个 ligands 批量生成多个 Boltz 输入文件，而不是把所有 ligands 塞进一个 affinity 任务。

### 2.6 AutoDock/Vina 可选兼容输出

可选支持：

- SDF 输出。
- PDBQT 输出，用于 AutoDock Vina / AutoDock-GPU。
- Gasteiger charge / torsion tree / rotatable bond 设置。
- docking-ready 文件和 manifest 对齐。

建议支持：

- MOL2 输出。
- AM1-BCC 或其他更高质量 charge 后端作为可选 worker。
- 保留不可旋转键配置。
- 对共价 docking / metal coordination / boron / silicon 等特殊元素给出显式 warning。

注意：PDBQT 不是 Boltz 输入格式。只有在用户选择 AutoDock/Vina 对接路线时才生成。

### 2.7 质量控制与报告

必须支持：

- 每个输入分子的处理状态：
  - success；
  - warning；
  - failed。
- 失败原因。
- 生成变体数。
- 生成 conformer 数。
- canonical SMILES。
- InChIKey。
- formal charge。
- heavy atom count。
- rotatable bond count。
- molecular weight。
- clogP / TPSA / HBD / HBA 等基础属性。

建议支持：

- Lipinski / Veber / lead-like / fragment-like 规则。
- PAINS / Brenk / reactive group 标注。
- 2D 结构缩略图。
- 3D conformer 预览。
- 批量筛选后的保留/删除列表。

### 2.8 输出资产

每次配体准备任务至少生成：

```text
prepared_ligands.sdf
boltz_inputs/
  <protein>_<ligand_id>.yaml
manifest.csv
failed.csv
report.json
```

如果用户选择 AutoDock/Vina 兼容输出，再额外生成：

```text
prepared_ligands.pdbqt
```

在资产层面建议拆成：

| 资产类型 | 用途 |
| --- | --- |
| `ligand` | 原始单配体 |
| `ligand_library` | 原始多分子库 |
| `prepared_ligand` | 单个准备后配体 |
| `prepared_ligand_library` | 准备后的多分子库 |
| `boltz_ligand_input` | 单个 Boltz ligand 输入片段，包含 chain id、SMILES/CCD |
| `boltz_prediction_input` | 完整 Boltz `input.yaml` 或批量 YAML |
| `ligand_conformer_set` | 多构象输出 |
| `docking_ready_ligand` | 可选 PDBQT 或其他 docking 专用输出 |

所有输出都必须能：

- 下载；
- 预览；
- 重命名；
- 复制到另一个项目；
- 被对接、FEP、SAR 页面作为输入资产选择。
- 被 Boltz 预测任务直接选择。

## 3. 推荐工具栈

### 3.1 RDKit：默认核心

用途：

- 分子解析和 sanitize。
- 标准化、去盐、metal disconnect、normalize、reionize、tautomer canonicalization。
- SMILES/SDF 读写。
- canonical SMILES / InChIKey。
- stereo 识别与枚举。
- ETKDG 3D 构象生成。
- MMFF/UFF 优化。
- 基础 descriptor 和过滤。

优点：

- BSD 3-Clause，适合商业产品集成。
- Python/C++ 生态成熟。
- 与 Pandas、FastAPI、worker 队列集成成本低。

限制：

- pH 相关质子化不是 RDKit 的强项，需要 Dimorphite-DL、Gypsum-DL、molscrub、OpenEye/Schrödinger 等补充。
- 对非常复杂的 macrocycle、金属配合物、特殊元素要做失败分流。

### 3.2 Boltz YAML 生成器：产品主输出

用途：

- 把 prepared ligand asset 转成 Boltz `sequences` 里的 `ligand` 条目。
- 为每个 ligand 生成稳定 chain id。
- 写入 `smiles` 或 `ccd`。
- 写入 `properties.affinity.binder`。
- 将 protein asset、ligand asset、pocket asset 组合成完整 `input.yaml`。
- 批量生成每个 ligand 一个 YAML，适合 affinity screening。

适合：

- Boltz 结构预测。
- Boltz-2 affinity 预测。
- 后续在网页端追踪每个 ligand 的预测结果。

限制：

- Boltz 不吃 SDF/PDBQT 作为 ligand 主输入；SDF 主要用于预览、审计和跨工具复用。
- 一个 affinity 任务只应绑定一个小分子 binder；批量筛选需要拆成多个 Boltz 输入。
- CCD 输入适合已在 CCD 中定义的配体或标准组分；自定义小分子优先走 SMILES。

### 3.3 Meeko：AutoDock/Vina 可选输出

用途：

- 生成 PDBQT。
- 分配 AutoDock atom types。
- partial charges。
- rotatable bonds / torsion tree。
- 对接输出再转回 RDKit/SDF。

适合：

- AutoDock Vina。
- AutoDock-GPU。
- 大规模 docking 工作流。

限制：

- 输入应已有显式氢和 3D 坐标；因此 Meeko 应放在 RDKit/Gypsum-DL/其他 3D 准备之后。
- 不是通用 ligand preparation 全流程替代品。

### 3.4 Gypsum-DL：开源状态枚举后端

用途：

- 从 SMILES 或 flat SDF 生成 3D-ready 小分子。
- 枚举 ionization、tautomer、chiral、cis/trans、ring conformer 状态。

适合：

- 开源虚拟筛选。
- pH 变体和环构象枚举需求强的批量准备。

限制：

- 项目相对老，吞吐、失败恢复、现代 Python 兼容性需要实测。
- 对超大、非 drug-like 分子可能很慢。

### 3.5 molscrub：AutoDock 生态里的批量准备

用途：

- RDKit ETKDGv3 + UFF。
- tautomer 枚举。
- pH correction。
- ring chair 枚举。
- 面向 AutoDock docking 的批量处理。

适合：

- 与 Meeko/Vina/AutoDock-GPU 一起做 docking-ready 流程。

限制：

- GPL-3.0，商业分发要谨慎。
- 文档和 API 稳定性需要实测。

### 3.6 Open Babel：格式转换和 fallback

用途：

- 多格式互转。
- `--gen3d` 生成 3D。
- `-p <pH>` pH 加氢。
- partial charge。
- 最小化。

适合：

- 格式兜底。
- 某些 RDKit 读写不方便的格式。
- 命令行 fallback。

限制：

- GPL；如果深度链接或分发要做 license 评估。
- 建议先作为可选 CLI worker，不要直接嵌入 WebServer 主流程。

### 3.7 商业对标后端

后续可做 adapter，不作为默认依赖：

| 工具 | 主要能力 | 适配方式 |
| --- | --- | --- |
| Schrödinger LigPrep + Epik | 高质量 ionization、tautomer、stereo、ring conformation、3D preparation | license 环境下 worker 调命令行 |
| OpenEye OMEGA + QUACPAC | 高速 conformer generation、tautomer/protonation、charges | license 环境下 worker 调 toolkit/app |

商业后端的价值是质量和吞吐，但部署、授权、成本都更复杂。架构上只需要预留 backend adapter，不要把产品逻辑绑定到单一商业工具。

## 4. 推荐开发框架

### 4.1 后端数据模型

新增或扩展：

```text
Job
  job_type = ligand_preparation
  input_asset_ids = [ligand or ligand_library]
  options_json = preparation parameters
  output_asset_ids = [prepared_ligand_library, boltz_prediction_input, optional docking_ready_ligand]
  result_json = stats, report paths, failed counts

Asset
  kind = ligand / ligand_library / prepared_ligand / prepared_ligand_library /
         boltz_ligand_input / boltz_prediction_input / docking_ready_ligand
  metadata_json = source mapping, generation options, chemistry summary

AssetFile
  role = input_sdf / prepared_sdf / boltz_yaml / boltz_yaml_bundle /
         pdbqt / manifest / failed / report / preview
```

### 4.2 Worker 入口

建议定义稳定 CLI：

```bash
boltz-ligand-prep \
  --input input.sdf \
  --input-format sdf \
  --output-dir /data/jobs/<job_id>/outputs \
  --mode boltz \
  --protein-asset-id <prepared_protein_asset_id> \
  --ligand-chain-prefix L \
  --affinity true \
  --pocket-asset-id <optional_pocket_asset_id> \
  --ph 7.4 \
  --ph-tolerance 1.0 \
  --enumerate-tautomers true \
  --enumerate-protomers true \
  --enumerate-undefined-stereo true \
  --max-variants-per-mol 16 \
  --max-conformers-per-variant 20 \
  --output-sdf true \
  --output-boltz-yaml true \
  --output-pdbqt false
```

worker 输出固定文件：

```text
prepared.sdf
boltz_inputs/
  input_<ligand_id>.yaml
manifest.csv
failed.csv
report.json
events.jsonl
```

### 4.3 Pipeline 阶段

```text
1. Load
   读 SDF/SMILES/CSV/XLSX/molblock

2. Validate
   sanitize、元素检查、重复 ID 检查、失败记录

3. Standardize
   normalize、去盐、metal disconnect、uncharge/reionize、canonical identifiers

4. Enumerate
   pH/protomer、tautomer、stereo、ring state

5. Generate 3D
   ETKDG/MMFF/UFF，多 conformer，失败 fallback

6. Filter / Rank
   energy、duplicate conformer、最大变体数、drug-like rules

7. Boltz Input
   生成 ligand chain id、SMILES/CCD、affinity binder、pocket/contact 约束、
   单分子或批量 YAML

8. Optional Docking Format
   用户明确选择 AutoDock/Vina 时，Meeko 写 PDBQT，保留 SDF 映射

9. Report
   manifest、failed、report、preview

10. Asset Commit
   输出写入 prepared_ligand_library / boltz_prediction_input /
   optional docking_ready_ligand
```

### 4.4 前端页面设计

配体处理页面建议拆成 5 个区域：

1. 输入区
   - 上传 SDF/MOL2/CSV/XLSX。
   - 粘贴 SMILES。
   - 手动画分子。
   - 从项目资产导入。

2. 分子表与单分子编辑区
   - 上传 SDF 或 SMILES 列表后，解析出分子表。
   - 每一行显示名称、SMILES、2D 缩略图、状态、来源行号。
   - 每个分子都有 `预览`、`编辑`、`复制为新分子`、`删除/保留`。
   - 点击 `编辑` 打开 Ketcher 这类 2D 分子编辑器。
   - 编辑保存后生成新 ligand asset 或 library 内新版本，不直接覆盖原始输入。

3. 列映射区
   - SMILES 列。
   - ID 列。
   - 名称列。
   - activity/series 透传列。

4. Boltz 输入区
   - ligand chain id。
   - ligand 输入方式：`smiles` 或 `ccd`。
   - 是否生成 affinity。
   - affinity binder 选择。
   - 是否绑定 pocket asset。
   - YAML 预览。

5. 准备参数区
   - pH。
   - 状态枚举开关。
   - stereo 策略。
   - conformer 数。
   - 输出格式：Boltz YAML / SDF / 可选 PDBQT。
   - 失败处理策略。

6. 预览与 QC 区
   - 输入分子表。
   - 2D 图。
   - 3D conformer。
   - warning/failed 分子。

7. 任务与输出区
   - 实时进度。
   - 成功/失败数量。
   - manifest。
   - prepared SDF 下载。
   - Boltz YAML 下载/预览。
   - 可选 PDBQT 下载。
   - 复制到项目。
   - 传给 Boltz 预测、docking/FEP/SAR。

### 4.5 API 草案

```text
POST /api/v1/assets/ligands/table
POST /api/v1/assets/ligands/smiles
POST /api/v1/assets/ligands/draw
POST /api/v1/assets/ligands/{asset_id}/molecules/{molecule_id}/edit

POST /api/v1/preparations/ligand
POST /api/v1/boltz-inputs
GET  /api/v1/jobs/{job_id}
GET  /api/v1/jobs/{job_id}/events
POST /api/v1/jobs/{job_id}/retry
POST /api/v1/jobs/{job_id}/cleanup

GET  /api/v1/assets/{asset_id}/files/{file_id}/download
POST /api/v1/assets/{asset_id}/copy
```

### 4.6 Docker 镜像建议

WebServer：

```text
python:3.11-slim
FastAPI + SQLAlchemy + Redis client
不安装大型化学计算依赖
```

ligand-prep-worker：

```text
python:3.11-slim 或 micromamba
RDKit
Boltz YAML builder
可选：Meeko / Gypsum-DL / molscrub / Open Babel CLI
```

商业 worker：

```text
schrodinger-worker
openeye-worker
通过 license server 或本地 license 文件启用
只暴露同一套 worker 输入/输出协议
```

## 5. MVP 开发顺序

### 第一阶段：可用

- SDF 上传。
- SMILES 列表。
- CSV/XLSX 选择 SMILES/name/id 列。
- 分子表展示。
- 单分子打开编辑器修改并保存为新资产。
- RDKit sanitize。
- 去盐、标准化、去重。
- 生成 Boltz-ready canonical SMILES。
- 生成 Boltz `input.yaml`。
- 生成 affinity binder 配置。
- 输出 prepared SDF。
- 输出 Boltz YAML。
- manifest / failed / report。
- 任务状态、重跑、清理输出。

### 第二阶段：Boltz 批量任务可用

- 一个蛋白 + 多个 ligands 批量生成多个 Boltz YAML。
- 每个 ligand 自动分配 chain id。
- 支持选择 pocket asset 生成 `constraints.pocket`。
- 支持 Boltz 预测页面直接选择 `boltz_prediction_input` 资产。
- 预测输出回写到 ligand manifest，供 SAR 排序。

### 第三阶段：对接兼容

- Meeko 输出 PDBQT。
- rotatable bond / charge / atom type 信息写入报告。
- 对接页面可直接选择 prepared ligand。
- 多分子库批量对接任务。

### 第四阶段：状态枚举

- pH/protomer。
- tautomer。
- undefined stereo。
- ring conformer。
- max variants 控制。
- 变体树和 warning 展示。

### 第五阶段：专业 QC

- PAINS/Brenk/reactive group。
- Lipinski/Veber/lead-like/fragment-like。
- macrocycle 策略。
- metal/organometallic 分流。
- 3D conformer viewer。

### 第六阶段：商业后端

- LigPrep/Epik adapter。
- OpenEye OMEGA/QUACPAC adapter。
- per-project backend selection。
- license/worker health check。

## 6. 关键风险

1. pH/tautomer 不是“唯一正确答案”
   - UI 必须显示生成了哪些状态，不能只吐一个结果。

2. stereo 不能乱改
   - 已定义手性默认保留。
   - 未定义手性才枚举，除非用户明确要求枚举全部。

3. 文件和分子映射不能丢
   - 每个输出分子必须保留 source row、source ID、variant index、conformer index。

4. Open Babel / molscrub license
   - GPL 组件不要直接混进主 WebServer。
   - 如要分发镜像，需要明确 license 策略。

5. 大规模库要流式处理
   - 不要一次把几十万分子全加载到 Web 进程内存。
   - worker 要按 chunk 写 manifest 和事件。

6. CADD 结果需要可解释
   - 每个删除、枚举、失败、warning 都要可追踪。

## 7. 调研来源

- Boltz prediction input format：<../docs/prediction.md>
- RDKit MolStandardize 文档：<https://www.rdkit.org/docs/source/rdkit.Chem.MolStandardize.rdMolStandardize.html>
- RDKit Overview / license：<https://www.rdkit.org/docs/Overview.html>
- Open Babel 3D generation：<https://openbabel.github.io/docs/3DStructureGen/Overview.html>
- Open Babel `obabel` 命令文档：<https://open-babel.readthedocs.io/en/latest/Command-line_tools/babel.html>
- Open Babel license FAQ：<https://openbabel.github.io/docs/Introduction/faq.html>
- Gypsum-DL GitHub：<https://github.com/durrantlab/gypsum_dl>
- Gypsum-DL paper：<https://pmc.ncbi.nlm.nih.gov/articles/PMC6534830/>
- molscrub GitHub：<https://github.com/forlilab/molscrub>
- Meeko ligand preparation：<https://meeko.readthedocs.io/en/develop/lig_prep_basic.html>
- Meeko overview：<https://meeko.readthedocs.io/en/develop/lig_overview.html>
- AutoDock Vina basic docking：<https://autodock-vina.readthedocs.io/en/latest/docking_basic.html>
- Schrödinger LigPrep：<https://www.schrodinger.com/platform/products/ligprep/>
- Schrödinger Epik：<https://www.schrodinger.com/platform/products/epik/>
- OpenEye OMEGA：<https://www.eyesopen.com/omega>
- OpenEye QUACPAC：<https://www.eyesopen.com/quacpac>
