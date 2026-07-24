# 分子生成 / Molecule Generation

## 作用 / Role

分子生成基于口袋资产做三维分子生成、扩展或 scaffold replacement。

Molecule generation uses pocket assets for 3D molecule generation, growth, and scaffold replacement.

## 输入 / Inputs

- `protein` 或 `prepared_protein` asset
- `pocket` asset
- 可选参考配体 / optional reference ligand

## 输出 / Outputs

- generated ligand candidates
- ligand library assets

## API / Automation

该模块当前是接口预留。输入衔接标准已经确定：从蛋白页保存的 `pocket.asset_id` 将作为生成任务的核心输入。

This module is currently a reserved entry. The chaining contract is fixed: `pocket.asset_id` saved from the protein page is the primary generation input.

