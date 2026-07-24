# 蛋白处理 / Protein Preparation

## 作用 / Role

蛋白处理把 PDB ID 或本地 PDB 文件变成后续对接、Boltz、FEP 和分子生成可复用的蛋白资产，并定义结合口袋。

Protein preparation converts a PDB ID or uploaded PDB into reusable receptor assets and binding pocket assets for docking, Boltz, FEP, and generation.

## 输入 / Inputs

- PDB ID 或 PDB 文件 / PDB ID or PDB file
- 链、配体、金属、水等对象选择 / chain, ligand, metal, and water selections
- 口袋中心与 box / pocket center and box

## 输出 / Outputs

- `protein` 或 `prepared_protein` asset
- `pocket` asset
- 可下载 PDB 文件 / downloadable PDB files

## API / Automation

```http
POST /api/v1/assets/proteins/pdb
POST /api/v1/assets/upload
POST /api/v1/assets/pockets
POST /api/v1/preparations/protein
```

自动化衔接：`prepared_protein.asset_id` 和 `pocket.asset_id` 可直接传给 Boltz input 或对接任务。

