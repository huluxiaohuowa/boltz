# Boltz

Boltz VOS 应用用于承载生物分子结构预测与蛋白-小分子亲和力预测工作流。

当前版本是 WebApp 开发模板，包含 VOS 应用入口、配置项、路由和 Compose
骨架。实际任务提交、输入准备、结果管理和推理调度能力会在后续开发中补齐。

## 访问入口

安装后从 VOS 左侧导航进入 Boltz，页面入口为：

```text
/app/com.ictrek.boltz/
```

## 配置项

- `BOLTZ_DATA_PATH`：Boltz 任务输入、输出和缓存目录。
- `MODEL_HUB_SHARED_MODELS_PATH`：可选挂载 Model Hub 共享模型目录。
- `BOLTZ_WEB_HOST_PORT`：可选暴露 Web 服务到宿主机的端口。

