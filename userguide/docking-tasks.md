# 对接任务 / Docking Tasks

## 作用 / Role

对接任务组合蛋白、配体和口袋，用于预测结合构象、筛选候选和生成 FEP 起点。

Docking tasks combine receptor, ligand, and pocket assets to predict binding poses, screen candidates, and seed FEP.

## 输入 / Inputs

- `prepared_protein` asset
- `ligand` 或 `prepared_ligand` asset
- `pocket` asset

## 输出 / Outputs

- `JobOut`
- 后续 result asset / future result assets

## API / Automation

```http
POST /api/v1/jobs
GET /api/v1/jobs?project_id=<project_id>
GET /api/v1/jobs/{job_id}/events
```

当前对接页先记录任务和输入关系；实际 docking/Boltz worker 接入后会通过 `output_asset_ids` 返回结果资产。

