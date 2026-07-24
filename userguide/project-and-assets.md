# 项目与资产 / Projects and Assets

## 作用 / Role

项目用于隔离同一用户的不同研究任务；资产是可复用的输入、输出和中间文件。

Projects separate research contexts for one user. Assets are reusable inputs, outputs, and intermediate files.

## 输入 / Inputs

- 项目名称 / project name
- 蛋白、配体、口袋、Boltz input、结果等资产 / protein, ligand, pocket, Boltz input, and result assets

## 输出 / Outputs

- `project_id`
- `asset_id`
- 可下载文件 / downloadable files

## API / Automation

```http
POST /api/v1/projects
GET /api/v1/projects
GET /api/v1/assets?project_id=<project_id>
PATCH /api/v1/assets/{asset_id}
POST /api/v1/assets/{asset_id}/copy
DELETE /api/v1/assets/{asset_id}
```

资产复制到其他项目时，网页会按项目名选择目标项目；API 使用目标 `project_id`。

