# 犬类数据端到端运行 — M6

*写给不熟悉生物信息学的工程师。无需生物学背景。*

---

## M6 做什么

M5 证明了云流水线能用仓库里已有人类 pVACtools 样本数据工作。M6 首次用真实犬类数据运行流水线：一个合成但生物学上有意义的体细胞 VCF，带 ROS_Cfam_1.0（CanFam4）坐标，经 VEP 注释，用 DLA 等位基因跑过 pVACseq，并由 Gemma 4 评分成一份临床报告。

这是系统首次为一只狗产出一个新抗原候选。

---

## 犬类 VCF

没有立即可用的、带 ROS_Cfam_1.0 坐标的公开体细胞 VCF，所以用 Ensembl REST API 的真实基因位置创建了一个合成 VCF。突变被放置在已知犬类肿瘤基因的编码区：

| 基因 | 突变 | 坐标 (ROS_Cfam_1.0) | VEP 后果 |
|---|---|---|---|
| TP53 | G→A | chr5:32669717 | missense (L26F) |
| TP53 | T→C | chr5:32669747 | intron_variant |
| BRCA2 | T→C | chr25:7891626 | upstream_gene_variant |
| BRCA2 | T→C | chr25:7891666 | upstream_gene_variant |
| PTEN | A→G | chr26:39409228 | missense (K62R) |
| PTEN | C→T | chr26:39409238 | synonymous |
| PIK3CA | G→A | chr34:12545798 | missense (V125M) |
| PIK3CA | G→A | chr34:12545828 | missense (E135K) |
| KIT | C→T | chr13:47757010 | synonymous |
| KIT | G→A | chr13:47757040 | synonymous |

写入 VCF 前，参考等位基因已在每个位置对照 Ensembl REST API 校验。

---

## VEP 注释

使用 VEP v115，带 `canis_lupus_familiaris` ROS_Cfam_1.0 缓存（含用于 HGVS 记法的参考 FASTA，约 1.5GB）。注释需要两个 pVACtools 特定插件：

- **Wildtype.pm** — 提供每个突变周围的野生型肽序列（pVACseq 计算突变表位所需）
- **Frameshift.pm** — 移码突变的下游序列（替换 pVACtools v4+ 中旧的 `Downstream.pm` 插件）

两个插件都随 pVACtools Python 包一起发布，位于 `pvactools/tools/pvacseq/VEP_plugins/`。普通的 `ensemblorg/ensembl-vep` Docker 镜像不包含它们——必须单独挂载。

pVACseq 所需的 VEP 标志（试出来的）：
```
--tsl                  # Transcript Support Level — pVACseq 拒绝没有它的 VCF
--hgvs --transcript_version  # HGVS 记法 — 蛋白变化识别所需
--pick                 # 每个变异一个后果（pVACseq 期望单后果格式）
--plugin Wildtype --plugin Frameshift
```

### Docker 卷挂载变通方案

WSL2 上的 Docker Desktop 在同一个源目录同时挂载到两个容器目标时会静默丢弃卷挂载（例如 `/data/input` 和 `/data/output` 都指向同一宿主路径）。变通方案：把输入 VCF 复制到 VEP 缓存目录，然后使用单个卷挂载。`annotation.py` 自动实现这一点。

---

## 用 DLA 等位基因的 pVACseq

NetMHCpan 4.2 恰好支持三个犬类 DLA 等位基因：
- `DLA-8803401`
- `DLA-8850101`
- `DLA-8850801`

原始提交表单预设中的 `DLA-12*00101` 等位基因不受支持，已被移除。

当算法名为 `NetMHCpan` 时，pVACseq 使用 IEDB REST API 调用 NetMHCpan（而非本地二进制）。本地二进制只需在 `$PATH` 中，pVACseq 才会接受该算法名。在云容器（`griffithlab/pvactools`）中，NetMHCpan 已预装。

pVACseq 还要求 VEP 注释中有 `--tsl`（Transcript Support Level），否则它会以清晰的错误消息拒绝该 VCF。

---

## 结果：一个强新抗原候选

| 字段 | 值 |
|---|---|
| 基因 | PIK3CA |
| 突变 | Val125Met (V→M) |
| 肽 | MPMCEFDMVK (10-mer) |
| DLA 等位基因 | DLA-8850801 |
| IC50 (突变) | 128.38 nM |
| IC50 (野生型) | 548.18 nM |
| 百分位排名 | 0.09% (top 0.1%) |
| 变化倍数 | 4.3× (肿瘤特异性) |

PIK3CA V125M 是一个生物学上合理的乳腺肿瘤突变。在 DLA 等位基因上 IC50 < 150 nM 是强结合者。野生型肽（MPVCEFDMVK）的 IC50 为 548 nM——突变驱动了 4 倍的结合亲和力提升，这是真正新抗原的标志。

---

## mRNA 设计

一个表位 → 251 nt mRNA 构体：
- CDS：42 nt（使用内嵌密码子表为犬类做密码子优化）
- GC 含量 (CDS)：54.8% — 在 45-60% 目标范围内
- 两侧为 beta-globin 5'UTR 和 3'UTR + 60-nt poly-A 尾

只有 1 个肽可用（对比通常请求的 3 个），所以 mRNA 构体是最小化的。一个有 5-10 个突变和更多通过候选的真实病例会产出一串多表位。

---

## 关键文件

| 文件 | 用途 |
|---|---|
| `pipeline/data/canine/canine_mammary_tumor_001.vcf` | 原始合成犬类体细胞 VCF |
| `pipeline/data/canine/canine_mammary_tumor_001_annotated.vcf` | VEP 注释后的 VCF（可供 pVACseq 使用） |
| `pipeline/vep_plugins/Wildtype.pm` | pVACtools VEP 插件，用于野生型肽序列 |
| `pipeline/vep_plugins/Frameshift.pm` | pVACtools VEP 插件，用于移码下游序列 |
| `pipeline/modules/annotation.py` | VEP Docker 包装器（单挂载变通方案，ROS_Cfam_1.0 默认值） |
| `pipeline/run_cloud.py` | Cloud Run 入口点（现支持 SKIP_PREDICTION + GCS_TSV_PATH） |

---

## 下一步（M6 剩余 + M7）

本地流水线运行已完成。仍待办：
- 通过 Web 应用提交注释后的犬类 VCF → 验证云流水线端到端运行
- 与 SME（Case 综合癌症中心研究人员）一起审阅临床报告质量
- 为黑客松提交录制视频

### 更新：富集演示数据集

在完成这个单 VCF 运行后，公开 `/demo` 病例被富集以产出更具视觉信息量的图表。富集数据集使用跨犬类乳腺肿瘤驱动基因的 18 个变异，产出 4 个强新抗原候选，横跨 TP53 和 PIK3CA。生物学忠于犬类乳腺肿瘤突变谱——与上面合成 VCF 针对的相同基因。演示中显示的合成规格书和临床报告是真实流水线输出，而非合成内容。
