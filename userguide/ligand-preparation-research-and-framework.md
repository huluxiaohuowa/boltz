# 配体准备功能清单与开发框架

本文面向 Boltz Workbench 的配体准备模块，目标是满足 CADD 研究人员在分子对接、Boltz 任务、虚拟筛选、SAR/FEP 后续分析中的常见配体准备需求。

## 1. 结论

第一版建议采用：

```text
WebApp / FastAPI
  负责：上传、表格列映射、参数配置、任务提交、任务状态、资产/文件管理

ligand-prep-worker
  负责：RDKit 主流程 + Meeko PDBQT 输出 + 可选 Gypsum-DL/Open Babel fallback

输出资产
  prepared_ligand / ligand_library / ligand_conformer_set / docking_ready_ligand
```

不要把重计算和复杂化学处理都塞进 WebServer 镜像。WebServer 应保持轻量；配体准备应走独立 worker，这样后续能按 CPU/GPU/商业软件 license 分开部署。

开源优先路线：

1. `RDKit` 作为核心化学对象、标准化、去盐、去重、SMILES/SDF 读写、stereo/conformer 的基础引擎。
2. `Meeko` 作为 AutoDock Vina / AutoDock-GPU 的 PDBQT 准备器。
3. `Gypsum-DL` 或 `molscrub` 作为状态枚举参考实现或可选后端。
4. `Open Babel` 作为格式转换和 fallback 工具，但不要优先把 Open Babel Python API 深度嵌入主程序，GPL 传播问题需要单独评估。
5. 商业适配层预留 `Schrödinger LigPrep/Epik` 和 `OpenEye OMEGA/QUACPAC`，但不作为默认依赖。

## 2. CADD 配体准备需要覆盖的功能

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

建议支持：

- PubChem CID / ChEMBL ID / vendor ID 导入。
- 从蛋白 PDB 里提取已结合配体，另存为 ligand asset。
- 从 prepared protein / docking result 中复制配体到配体准备页面。

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

### 2.5 电荷、原子类型和对接格式

必须支持：

- SDF 输出。
- PDBQT 输出，用于 AutoDock Vina / AutoDock-GPU。
- Gasteiger charge / torsion tree / rotatable bond 设置。
- docking-ready 文件和 manifest 对齐。

建议支持：

- MOL2 输出。
- AM1-BCC 或其他更高质量 charge 后端作为可选 worker。
- 保留不可旋转键配置。
- 对共价 docking / metal coordination / boron / silicon 等特殊元素给出显式 warning。

### 2.6 质量控制与报告

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

### 2.7 输出资产

每次配体准备任务至少生成：

```text
prepared_ligands.sdf
prepared_ligands.pdbqt        # 如果选择 AutoDock/Vina 输出
manifest.csv
failed.csv
report.json
```

在资产层面建议拆成：

| 资产类型 | 用途 |
| --- | --- |
| `ligand` | 原始单配体 |
| `ligand_library` | 原始多分子库 |
| `prepared_ligand` | 单个准备后配体 |
| `prepared_ligand_library` | 准备后的多分子库 |
| `ligand_conformer_set` | 多构象输出 |
| `docking_ready_ligand` | PDBQT 或 docking 专用输出 |

所有输出都必须能：

- 下载；
- 预览；
- 重命名；
- 复制到另一个项目；
- 被对接、FEP、SAR 页面作为输入资产选择。

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

### 3.2 Meeko：AutoDock/Vina 输出

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

### 3.3 Gypsum-DL：开源状态枚举后端

用途：

- 从 SMILES 或 flat SDF 生成 3D-ready 小分子。
- 枚举 ionization、tautomer、chiral、cis/trans、ring conformer 状态。

适合：

- 开源虚拟筛选。
- pH 变体和环构象枚举需求强的批量准备。

限制：

- 项目相对老，吞吐、失败恢复、现代 Python 兼容性需要实测。
- 对超大、非 drug-like 分子可能很慢。

### 3.4 molscrub：AutoDock 生态里的批量准备

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

### 3.5 Open Babel：格式转换和 fallback

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

### 3.6 商业对标后端

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
  output_asset_ids = [prepared_ligand_library, docking_ready_ligand]
  result_json = stats, report paths, failed counts

Asset
  kind = ligand / ligand_library / prepared_ligand / prepared_ligand_library / docking_ready_ligand
  metadata_json = source mapping, generation options, chemistry summary

AssetFile
  role = input_sdf / prepared_sdf / pdbqt / manifest / failed / report / preview
```

### 4.2 Worker 入口

建议定义稳定 CLI：

```bash
boltz-ligand-prep \
  --input input.sdf \
  --input-format sdf \
  --output-dir /data/jobs/<job_id>/outputs \
  --mode docking \
  --ph 7.4 \
  --ph-tolerance 1.0 \
  --enumerate-tautomers true \
  --enumerate-protomers true \
  --enumerate-undefined-stereo true \
  --max-variants-per-mol 16 \
  --max-conformers-per-variant 20 \
  --output-sdf true \
  --output-pdbqt true
```

worker 输出固定文件：

```text
prepared.sdf
prepared.pdbqt
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

7. Docking Format
   Meeko 写 PDBQT，保留 SDF 映射

8. Report
   manifest、failed、report、preview

9. Asset Commit
   输出写入 prepared_ligand_library / docking_ready_ligand
```

### 4.4 前端页面设计

配体处理页面建议拆成 5 个区域：

1. 输入区
   - 上传 SDF/MOL2/CSV/XLSX。
   - 粘贴 SMILES。
   - 手动画分子。
   - 从项目资产导入。

2. 列映射区
   - SMILES 列。
   - ID 列。
   - 名称列。
   - activity/series 透传列。

3. 准备参数区
   - pH。
   - 状态枚举开关。
   - stereo 策略。
   - conformer 数。
   - 输出格式。
   - 失败处理策略。

4. 预览与 QC 区
   - 输入分子表。
   - 2D 图。
   - 3D conformer。
   - warning/failed 分子。

5. 任务与输出区
   - 实时进度。
   - 成功/失败数量。
   - manifest。
   - prepared SDF/PDBQT 下载。
   - 复制到项目。
   - 传给 docking/FEP/SAR。

### 4.5 API 草案

```text
POST /api/v1/assets/ligands/table
POST /api/v1/assets/ligands/smiles
POST /api/v1/assets/ligands/draw

POST /api/v1/preparations/ligand
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
Meeko
可选：Gypsum-DL / molscrub / Open Babel CLI
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
- RDKit sanitize。
- 去盐、标准化、去重。
- 3D conformer 生成。
- 输出 prepared SDF。
- manifest / failed / report。
- 任务状态、重跑、清理输出。

### 第二阶段：对接可用

- Meeko 输出 PDBQT。
- rotatable bond / charge / atom type 信息写入报告。
- 对接页面可直接选择 prepared ligand。
- 多分子库批量对接任务。

### 第三阶段：状态枚举

- pH/protomer。
- tautomer。
- undefined stereo。
- ring conformer。
- max variants 控制。
- 变体树和 warning 展示。

### 第四阶段：专业 QC

- PAINS/Brenk/reactive group。
- Lipinski/Veber/lead-like/fragment-like。
- macrocycle 策略。
- metal/organometallic 分流。
- 3D conformer viewer。

### 第五阶段：商业后端

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

