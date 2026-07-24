# FEP 与分析 / FEP and Analysis

## 作用 / Role

FEP/分析模块用于后续自由能计算、轨迹检查、误差分析和报告输出。

FEP/analysis is reserved for free-energy calculations, trajectory inspection, uncertainty analysis, and reports.

## 输入 / Inputs

- prepared complex or docking result
- ligand series
- simulation settings

## 输出 / Outputs

- ΔG / ΔΔG tables
- trajectories
- analysis reports

## API / Automation

当前为规划入口；后续 worker 会通过 `POST /api/v1/jobs` 创建任务，并用 `output_asset_ids` 返回结果资产。

