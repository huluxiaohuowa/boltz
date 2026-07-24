# 管理 / Admin

## 作用 / Role

管理页用于审核用户、查看全局任务、停止/清理/删除任务，以及查看部署机器资源。

The admin page approves users, monitors global jobs, cancels/cleans/deletes jobs, and displays host resources.

## 输入 / Inputs

- admin token
- username
- job_id

## 输出 / Outputs

- user status
- global JobOut list
- CPU, memory, GPU, disk, and architecture metrics

## API / Automation

```http
GET /api/v1/admin/users
POST /api/v1/admin/users/{username}/approve
DELETE /api/v1/admin/users/{username}
GET /api/v1/admin/jobs
POST /api/v1/admin/jobs/{job_id}/cancel
POST /api/v1/admin/jobs/{job_id}/cleanup
DELETE /api/v1/admin/jobs/{job_id}
GET /api/v1/admin/system
```

删除用户会级联停止并删除该用户任务、项目、资产和持久化文件。

