# AlphaFold2 结构验证集成方案

> 本文档记录 Project Rosie 引入 AlphaFold2 做新抗原表面暴露验证的完整分析与环境准备方案。
> 对应 `docs/explainers/02-key-decisions.cn.md` 中"决策 3 —— 第一阶段不使用 AlphaFold"的 Phase 2 落地计划。

## 1. 背景与目标

当前流水线（Phase 1）的候选排序仅基于 IC50 + 免疫原性 + VAF 的确定性打分，
**缺少结构层面的验证**——前 20 名候选中有些可能位于蛋白质内部（未暴露于表面），
较难被 T 细胞接触。

本方案的目标：

- 对 top 候选表位对应的蛋白做结构预测
- 提取 **pLDDT 置信度** 和 **突变位点表面暴露性（SASA）**
- 作为硬过滤条件加入 `scoring.py`，兑现决策 3 中承诺的 Phase 2 过滤

关键简化：新抗原的表面暴露检查用**野生型蛋白结构**即可（点突变通常不改变整体折叠），
同一蛋白的多个候选表位只需预测一次结构。Top 20 候选通常落在 10–20 个不同蛋白上。

## 2. 方案选型

| 方案 | 说明 | 结论 |
|---|---|---|
| 方案 1：AlphaFold 结构数据库 | 下载 DeepMind 预计算结构（mmCIF），Biopython 算 SASA。零 GPU | 仅覆盖人类蛋白，犬类核心用例不适用 |
| **方案 2：AlphaFold2 官方 Docker 镜像** | 完全离线，GPU 推理，支持任意物种 | ✅ **选定**（本机有 GPU 资源） |
| 方案 3：ColabFold | 免费但非离线，依赖 Google 服务器 | 不符合离线要求 |
| 备选：OpenFold / ESMFold | OpenFold 与 AF2 相当；ESMFold 15B 需 ~30GB 显存 | 若 AF2 镜像有问题可切换 |

## 3. GPU 资源评估

本机配置：3 × NVIDIA RTX 5000 Ada（32 GB），驱动 580.159.03，CUDA 13.0。

**瓶颈：ollama `llama-server` 同时占用三张卡（14–17 GB/卡）。**

| GPU | 总显存 | ollama 占用 | 可用 |
|---|---|---|---|
| GPU 0 | 32 GB | 13.9 GB | ≈ 18.8 GB |
| GPU 1 | 32 GB | 14.2 GB | ≈ 18.3 GB |
| GPU 2 | 32 GB | 17.3 GB | ≈ 15.4 GB |

各方案显存需求：

| 方案 | 显存需求 | 结论 |
|---|---|---|
| AlphaFold2（默认 5 recycles / 20 sampling） | ~16–20 GB | ⚠️ 勉强够（GPU 0/1）；建议 `num_recycles` 降到 2–3 |
| ESMFold + ESM2-15B | ~30 GB | ❌ 放不下 |
| ESMFold + ESM2-8B | ~16 GB | ⚠️ 勉强够，精度较低 |

**结论：资源够用，前提是跑 AF2 前把 ollama 从目标 GPU 上移走**
（`ollama stop` 或 `CUDA_VISIBLE_DEVICES` 固定 ollama 到单卡）。
腾出 2 张完整 32 GB 卡后可并行跑 2 个蛋白。

时间预估（Ada 卡比 T4 快 2–3 倍）：

- 单蛋白（~400 aa）：约 10–20 分钟
- Top 20 候选（去重后 10–20 个蛋白）：串行约 2–6 小时，双卡并行减半

## 4. 与现有 Docker 环境的兼容性

**结论：不冲突。** 仓库现有三个 Docker 文件与 AF2 官方镜像完全独立：

| 文件 | 用途 | 基础镜像 |
|---|---|---|
| `Dockerfile`（根目录） | Next.js 前端 | `node:22-alpine` |
| `pipeline/Dockerfile` | 流水线（pVACseq + MHCflurry + Gemma） | `griffithlab/pvactools:latest` |
| `pipeline/docker-compose.yml` | VEP 注释 | `ensemblorg/ensembl-vep` |

AF2 官方镜像是**自包含的工具容器**（输入 FASTA → 输出 PDB + pLDDT JSON），
与现有容器只通过**挂载卷**交换数据，不共享 Python 环境、端口或网络。
pipeline 镜像保持 CPU-only 不变，无需安装任何 GPU 库。

集成架构（零侵入）：

```
pipeline 容器 (pvactools)          alphafold 容器 (独立)
┌─────────────────────┐           ┌─────────────────────┐
│ run_pipeline.py     │  写入     │  官方 AF2 镜像       │
│   ↓                 │  FASTA ──→│  (GPU, 独立进程)     │
│ structure.py        │           │                     │
│   ↓ 读取 PDB+pLDDT  │←── 挂载 ──│  输出: *.pdb, *.json │
│   ↓ SASA 计算       │  卷      │                     │
│ scoring.py (过滤)   │           └─────────────────────┘
└─────────────────────┘
```

`structure.py` 在 pipeline 容器内用 `subprocess` 调用
`docker run --gpus '"device=0"' <af2-image> ...`，
挂载共享卷传入 FASTA、读回 PDB。

**实现模式参考 `pipeline/modules/annotation.py`**（VEP wrapper）：
同样的"单挂载卷 + 临时文件进出"模式，可规避 WSL2/Docker 卷冲突
（`annotation.py` 中已有此注释与 `chmod 0o666` 处理）。

## 5. 环境准备步骤

1. **检查磁盘空间**：AF2 镜像约 10–20 GB，先 `docker system df` 确认
2. **拉取镜像**：`docker pull` 官方镜像（⚠️ 具体 repo 路径和 tag 待确认，避免拉错）
3. **冒烟测试**：用 ~150 aa 的小蛋白 FASTA 跑一次预测，验证 GPU 透传 + 输出格式
4. **确认输出**：检查 `*.pdb` 和 `*.json`（含 per-residue pLDDT）是否落在挂载卷里

## 6. 后续集成计划（待实施）

1. 新增 `pipeline/modules/structure.py`：
   输入 top 候选的蛋白 + 突变位点 → 输出每个候选的 `pLDDT` 和 `surface_exposed: bool`
2. `pipeline/modules/scoring.py` 增加硬过滤：
   `pLDDT < 70` 或 SASA 低于阈值的候选剔除
3. `run_pipeline.py` 加 `--structure` 开关，默认关闭，保持现有 CPU-only 行为不变
4. 前端：`CandidatesTable.tsx` / `PipelineTimeline.tsx` 的 scoring 步骤展示 pLDDT 列

## 7. 待确认项

- [ ] AF2 官方 Docker 镜像的确切 repo 路径与推荐 tag（发布在 ghcr.io）
- [ ] 跑 AF2 前 ollama 腾卡的具体操作方式
- [ ] Docker 容器需 `--gpus '"device=0"'` 指定单卡，避免把 ollama 占用的显存算进去导致 OOM
