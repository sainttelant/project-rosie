# 架构与端到端运行流程

*Project Rosie 的权威工程参考文档。本文描述的是**代码当前实际的状态**——下文每个文件路径、端点、阶段回调都已对照源码核实。它是对 `docs/explainers/` 中面向生物学的叙述性讲解以及 `docs/hackathon-writeup.md` 的补充。当某篇旧讲解文档与本文不一致时，以本文（反映线上代码）为准。*

> 中文版本。英文原版见 [`architecture-and-flow.md`](./architecture-and-flow.md)。

---

## 一句话概览（TL;DR）

Project Rosie 是一个**面向肿瘤科医生的 AI 临床助手，从兽医场景切入**。用户上传一份**经过 VEP 注释的肿瘤 VCF**（记录癌症活检中体细胞突变的表格）；系统在不到一小时内、以几美元算力产出：

1. **排序好的新抗原疫苗靶点列表**（top 20，带评分）
2. **可直接合成、密码子优化后的 mRNA 疫苗序列**（FASTA）
3. **白话临床报告**（Gemma 4 阅读数据 *以及* 两张图后撰写）
4. **CMO 级别的 mRNA 合成规格书**（确定性 Jinja 模板，非 LLM 生成）
5. **两张诊断图**（结合亲和力柱状图、突变谱饼图）

### 三套运行时

| 子系统 | 运行时 | 位置 |
|---|---|---|
| Web 应用 + API | Node.js — Next.js 16 App Router（部署在 Vercel） | `src/` |
| 生信流水线 | Python（pVACtools、NetMHCpan、Biopython、pandas）打包为 Docker 镜像，跑在 **Cloud Run Jobs** | `pipeline/` |
| 智能层 | **Gemma 4** via Vertex AI —— 两个子系统都会调用 | — |
| 状态 + 鉴权 | Supabase（PostgreSQL + 行级安全 RLS + Realtime） | `supabase/` |
| 文件存储 | Google Cloud Storage（VCF 上传，30 天生命周期） | — |

### 组织一切的那条规则

> **确定性代码负责生物学；Gemma 负责解读。**

评分、mRNA 设计、合成规格都是透明、可审计的 Python + 模板。Gemma 只用在"推理"本身是关键的地方：在昂贵的计算*之前*给建议、在*之后*写报告、对交互式"what-if"阈值变化做解说、以及回答自由提问。模型输出的任何内容都不会改变排序结果或 mRNA 序列。

---

## 系统产出什么，以及落地在哪里

| 产出 | 生产者 | 存储位置 | 呈现于 |
|---|---|---|---|
| 排序候选（top 20） | `pipeline/modules/scoring.py` | `cases.candidates_json`（JSONB） | `CandidatesTable`、`SensitivityPanel` |
| 结合亲和力柱状图（PNG） | `pipeline/modules/visualizations.py` | `cases.binding_affinity_img_b64` | `ReportViewer` |
| 突变谱饼图（PNG） | `pipeline/modules/visualizations.py` | `cases.mutation_landscape_img_b64` | `ReportViewer` |
| 临床报告（Markdown） | `pipeline/modules/gemma.py`（Gemma 4） | `cases.clinical_report_md` | `ReportViewer`、经 `/api/cases/[id]/download` 打印/PDF |
| mRNA 构体（FASTA） | `pipeline/modules/mrna_design.py` | `cases.mrna_fasta` | `MRNAViewer`、`.fasta` 下载 |
| 合成规格书（Markdown） | `pipeline/modules/synthesis_spec.py`（Jinja） | `cases.mrna_summary_md` | `ReportViewer`、打印/PDF 下载 |
| 汇总统计 | `pipeline/modules/scoring.py` | `cases.total_mutations`、`cases.candidates_after_filtering` | 时间线、仪表盘 |

---

## 仓库结构

```
project-rosie/
├── src/                          # Next.js 16 应用（前端 + API 路由），TypeScript
│   ├── app/
│   │   ├── (app)/                # 需登录的诊所区
│   │   │   ├── dashboard/        # 病例列表（GET /api/cases）
│   │   │   ├── submit/           # 新建病例：VCF 上传 + 预检 + 提交
│   │   │   └── cases/[id]/       # 实时状态时间线 + 报告 + 聊天 + 敏感性
│   │   ├── (public)/             # 概览、文档、writeup、架构、demo 页
│   │   ├── auth/                 # 登录 / 注册 / 回调（Supabase 鉴权）
│   │   └── api/                  # API 路由（见下方"API 路由"表）
│   ├── components/               # PipelineTimeline、ReportViewer、ChatWidget、
│   │   │                         # VcfAdvisor、SensitivityPanel、CandidatesTable、…
│   │   └── ui/                   # shadcn 风格基础组件
│   ├── lib/
│   │   ├── gcp-auth.ts           # GCP 令牌：JSON key / WIF-OIDC / ADC 兜底
│   │   ├── vcf-stats.ts          # 浏览器端 VCF 结构解析器（供 VcfAdvisor 用）
│   │   ├── sensitivity.ts        # 客户端 what-if 重排（镜像 scoring.py 阈值）
│   │   ├── supabase/{client,server}.ts   # @supabase/ssr（浏览器 + 服务端 + 管理员）
│   │   └── utils.ts
│   ├── types/case.ts             # 共享 TS 类型（Candidate、CandidatesJson、…）
│   └── proxy.ts                  # Next.js 中间件/代理钩子
├── pipeline/                     # Python 生信流水线（Cloud Run Jobs 目标）
│   ├── run_cloud.py              # Cloud Run 入口——环境变量配置，POST 进度回调
│   ├── run_pipeline.py           # 本地 CLI 入口（同样阶段，无云）
│   ├── Dockerfile                # FROM griffithlab/pvactools + NetMHCpan 4.2 + 依赖
│   ├── modules/
│   │   ├── prediction.py         # 封装 `pvacseq run`
│   │   ├── scoring.py            # 硬过滤 + 综合评分 → candidates JSON
│   │   ├── visualizations.py     # 两张 matplotlib PNG
│   │   ├── gemma.py              # Gemma 4 多模态临床报告
│   │   ├── mrna_design.py        # 密码子优化的多表位 mRNA → FASTA
│   │   ├── synthesis_spec.py     # Jinja CMO 合成规格
│   │   ├── annotation.py         # 经 Docker 跑 VEP（本地 / 犬科预处理）
│   │   └── __init__.py
│   ├── templates/synthesis_spec.md.j2
│   ├── vep_plugins/{Wildtype.pm,Frameshift.pm}
│   ├── scripts/{build_demo.py,wipe_and_seed_demo.py}
│   └── requirements.txt
├── supabase/
│   ├── config.toml
│   └── migrations/20260508000001_cases.sql   # `cases` 表 + RLS + Realtime
├── scripts/
│   ├── gcs-lifecycle.json        # 流水线工作文件 30 天自动删除
│   └── seed_demo.py              # 种入公开 demo 病例（user_id IS NULL）
├── .github/workflows/supabase-keepalive.yml
├── docs/                         # 本文档 + 讲解 + 博客 + writeup
└── README.md
```

---

## 架构一览

```
                        ┌──────────────────────────────────────────────┐
                        │                 浏览器（Vercel）              │
  Supabase Realtime ◄───┤  提交 → cases/[id] 时间线 → 报告/聊天          │
  （WebSocket 推送）     └───────┬───────────────────────────┬──────────┘
                                 │  POST /api/cases          │ POST /api/cases/{id}/chat
                                 ▼                          │ /sensitivity-narrate
                        ┌───────────────────┐               │ /api/vcf-advisor
                        │  Next.js API (Node)│──────────────┤
                        │  鉴权：Supabase    │   GCP 令牌    │   （Gemma 4 via Vertex AI）
                        └───┬─────────┬─────┘               │
        POST /api/upload    │         │ 触发 Job             ▼
        （multipart→GCS）   ▼         ▼
                ┌──────────────┐   ┌────────────────────────────────────┐
                │  GCS 存储桶   │   │   Cloud Run Job（Docker 容器）      │
                │  （VCF 文件） │   │   ENTRYPOINT: python run_cloud.py  │
                └──────┬───────┘   │  ┌──────────┬────────┬───────────┐ │
                   读取│          │  │ 预测     │ 评分   │  可视化    │ │
                       └──────────►│  │(pVACseq) │(排序) │  (图表)    │ │
                                   │  └──────────┴────────┴───────────┘ │
                                   │  ┌────────────┬──────────────────┐ │
                                   │  │ gemma.py   │ mrna_design +    │ │
                                   │  │(临床报告)   │ synthesis_spec   │ │
                                   │  │            │  (FASTA/CMO 文档) │ │
                                   │  └────────────┴──────────────────┘ │
                                   └──────────────────┬─────────────────┘
                                                      │ POST /api/cases/{id}/progress
                                                      │ Authorization: Bearer PIPELINE_CALLBACK_SECRET
                                                      ▼
                        ┌──────────────────────────────────────────────────┐
                        │   Supabase（Postgres）— `cases` 表（RLS）        │
                        │   每次阶段更新 → Realtime 推送 → 浏览器           │
                        └──────────────────────────────────────────────────┘
```

---

## 端到端运行流程

一次完整提交的旅程，按阶段拆解。文件路径即实际执行的代码。

### 阶段 0 — 鉴权

Supabase 鉴权（邮箱 + OTP，通过 `@supabase/ssr` 接入）。服务端路由经 `src/lib/supabase/server.ts` → `supabase.auth.getUser()` 读取 cookie。每个 `cases` 行都带上用户 id，并由行级安全（见"数据模型"）约束：用户只能触碰自己的行。**公开 demo** 行的 `user_id IS NULL`，无需鉴权即可读取（供 `/demo` 使用；聊天/敏感性路由也会按 `user_id IS NULL` 分支处理）。

### 阶段 1 — 提交：上传 VCF

代码：`src/app/(app)/submit/page.tsx` → `handleSubmit()`。

1. 用户输入**样本名**、选择**物种**（默认 `canis_lupus_familiaris`）、确认 **MHC/DLA 等位基因**（按物种预置）。
2. 选择文件后，`VcfAdvisor` 在提交**之前**运行（Gemma 4 角色 1，见下文）：`src/lib/vcf-stats.ts` 在浏览器端解析前 ~5 MB，提取结构事实（变异数、INFO key、TUMOR/NORMAL 列、体细胞标记、染色体、FILTER 值）；`POST /api/vcf-advisor` 返回 0–3 条建议。**绝不阻塞提交**——任何失败都退化为 `{ notes: [] }`。该路由还会先做确定性检查：是否存在 `CSQ` INFO key（pVACseq 需要 VEP 注释），再决定是否花一次 Gemma 调用。
3. **上传**：`POST /api/upload`（`src/app/api/upload/route.ts`）以 `multipart/form-data` 接收文件，用 `uploadType=media` 流式上传到 GCS 的 `vcf/{user.id}/{timestamp}/{filename}`。返回 `gcsPath` 形如 `gs://bucket/...`。
   > **关于线上上传路径的说明。** 提交页用的是 `POST /api/upload`（文件*经过* Next.js）。另有一条路由 `GET /api/upload-url`（`uploadType=resumable`，浏览器直传 GCS）也存在，但**并非**当前提交页所调用。`docs/explainers/04-cloud-deployment.md` 把 resumable 路径描述为线上路径——这是陈旧点。
4. **创建病例**：`POST /api/cases`（`src/app/api/cases/route.ts`），参数 `{ sample_name, species, alleles, gcs_vcf_path }`。
   - 强制**10 次提交上限**（超限返回 `429`）。
   - 插入 `cases` 行，`status: "running"`。
   - 调用 `triggerPipelineJob()` → `POST https://run.googleapis.com/v2/projects/{project}/locations/{region}/jobs/{job}:run`，注入每次运行的环境变量（`CASE_ID`、`GCS_VCF_PATH`、`SAMPLE_NAME`、`ALLELES`、`SPECIES`、`CALLBACK_URL`、`PIPELINE_CALLBACK_SECRET`、`GCS_BUCKET`、`GCP_PROJECT_ID`、`GEMMA_MODEL`）。
   - 等待触发结果；若失败，把该行标记为 `failed` 并返回 `500`。
   - 成功返回 `{ id }`，状态码 `201`。
5. 浏览器跳转到 `/cases/{id}`。

### 阶段 2 — 实时状态追踪

`/cases/{id}/page.tsx`（客户端）+ `PipelineTimeline` 订阅 `cases` 表的 Supabase Realtime 通道（迁移中已加入 `supabase_realtime`）。流水线每 POST 一次阶段更新，行就变化，Supabase 经 WebSocket 推送，UI 重绘时间线——**无轮询、无刷新**。

### 阶段 3 — Cloud Run 流水线（`pipeline/run_cloud.py`）

所有配置通过环境变量传入。该 Job：

1. `callback("running")`。
2. 从 GCS 下载 VCF 到临时目录。
3. **阶段 1 — 预测**（`modules/prediction.py:run_pvacseq`）：执行
   `pvacseq run <vcf> <vcf-sample-id> <alleles> <algo> <out> -e1 8,9,10,11 -m median -b 500 -c 1`。
   它读取 VCF `#CHROM` 头里的*真实*样本列（用户填的显示名对不上）。输出：`MHC_Class_I/{sample}.MHC_I.all_epitopes.tsv`。
   > 可选 `SKIP_PREDICTION=true` 路径改为从 `GCS_TSV_PATH` 加载预先算好的 TSV。
4. **阶段 2 — 评分**（`modules/scoring.py:score_candidates`）：硬过滤（`IC50 ≤ 500 nM`、`Tumor VAF ≥ 0.01`），再按综合评分 `0.50·IC50 + 0.30·免疫原性 + 0.20·VAF`，保留 **top 20** → candidates JSON。`callback("scoring")` 在前后各发一次（之后那次携带 `total_mutations` + `candidates_after_filtering`）。
5. **阶段 3 — 可视化**（`modules/visualizations.py:generate_all`）：matplotlib（无头 `Agg`）→ 结合亲和力柱状图 + 突变谱饼图（两张 PNG）。`callback("reporting")`。
6. **阶段 4 — 临床报告**（`modules/gemma.py:generate_clinical_report`）：Gemma 4（Vertex AI）读取 candidates JSON **以及**两张 PNG（多模态），在按物种区分的系统提示下撰写 400–600 字报告；随后 `_embed_images` 注入图表引用。
7. **阶段 5 — mRNA 设计**（`modules/mrna_design.py:design_mrna`）：取 top 3 表位用 `AAY` 连接子串联，包裹为 `5'UTR → Kozak+ATG → CDS → 3'UTR → poly-A(60)`，用犬科每个氨基酸的最高频密码子做优化 → FASTA + 一份 Markdown 设计摘要。`callback("designing")`。
8. **阶段 5b — 合成规格**（`modules/synthesis_spec.py:generate_synthesis_spec`）：渲染 `templates/synthesis_spec.md.j2`（Jinja）为 CMO 级别的订单文档。**非致命**——出错时回退到设计摘要。
9. **收尾**：`callback("completed", candidates_json, clinical_report_md, mrna_fasta, mrna_summary_md, binding_affinity_img_b64, mutation_landscape_img_b64)`。

任一阶段抛异常 → `callback("failed", error_message=...)` 且 `sys.exit(1)`。

**阶段 → `cases.status` 映射：**

| 流水线节点 | `status` 取值 |
|---|---|
| Job 启动 | `running` |
| 评分（前 + 后） | `scoring` |
| 可视化 + 报告 | `reporting` |
| mRNA 设计 | `designing` |
| 全部完成 | `completed` |
| 任一异常 | `failed` |

> `callback()` 助手对 `completed`/`failed` 最多重试 4 次（它们必须送达，否则病例会永远卡住）；非关键更新为尽力而为（1 次）。若关键回调始终无法送达，则非零退出，让 Cloud Run 记录到该失败。

### 阶段 4 — 回调写入数据库

`POST /api/cases/[id]/progress`（`src/app/api/cases/[id]/progress/route.ts`）：

- 校验 `Authorization: Bearer {PIPELINE_CALLBACK_SECRET}`（共享密钥，**非**用户鉴权）。
- 使用**管理员/service-role** 客户端（`createAdminClient`）以绕过 RLS、可写该行。
- 合并任意子集字段：`status`、统计、`candidates_json`、`clinical_report_md`、`mrna_fasta`、`mrna_summary_md`、两张 base64 图、`error_message`，并更新 `updated_at`。

由于该更新发生在 `cases` 表上，**Supabase Realtime 会把它扇出到浏览器**（阶段 2）。当 `status` 到达 `completed`，报告查看器、mRNA 查看器与图表即从该行渲染。

### 阶段 5 — 阅读结果与后续操作

在 `/cases/{id}`（以及公开 `/demo`）上：

- **`ReportViewer`** 渲染临床报告 Markdown（含两张图），并提供打印/PDF。
- **`MRNAViewer`** 渲染密码子优化后的 mRNA 构体。
- **`CandidatesTable`** 展示排序后的 top 候选。
- **`SensitivityPanel`**（`src/lib/sensitivity.ts`）在用户拖动 IC50/VAF 滑块时**客户端即时重排**（零 LLM 成本）；按需调用 `POST /api/cases/[id]/sensitivity-narrate` 获取 Gemma 4 的 1–2 句解说。
- **`ChatWidget`** → `POST /api/cases/{id}/chat`，围绕本病例的候选 + 报告做自由问答。
- **下载** → `GET /api/cases/[id]/download?type=report-pdf|fasta|synthesis-pdf`：
  - `report-pdf` / `synthesis-pdf` 返回带样式、面向打印的 HTML 文档（自动 `window.print()`），图片以内联 base64 data URI 呈现。
  - `fasta` 以文件附件形式返回 mRNA FASTA。

### API 路由一览

| 路由 | 方法 | 鉴权 | 用途 |
|---|---|---|---|
| `/api/cases` | GET, POST | 用户（cookie） | 列出我的病例；创建病例并触发 Cloud Run |
| `/api/cases/[id]` | GET, DELETE | 用户 | 取单个病例；删除它 |
| `/api/cases/[id]/progress` | POST | 共享密钥 | 流水线阶段回调 → 写 `cases` 行 |
| `/api/cases/[id]/chat` | POST | 用户 *或* demo | 关于本病例的 Gemma 4 问答 |
| `/api/cases/[id]/sensitivity-narrate` | POST | 用户 *或* demo | 对 what-if 阈值的 Gemma 4 解说 |
| `/api/cases/[id]/download` | GET | 用户 | report-pdf / fasta / synthesis-pdf |
| `/api/upload` | POST | 用户 | multipart VCF → GCS（线上路径） |
| `/api/upload-url` | GET | 用户 | GCS resumable 上传 URI（备选） |
| `/api/vcf-advisor` | POST | 用户 | Gemma 4 提交前 VCF 预检 |
| `/auth/callback`、`/auth/login`、`/auth/signup` | — | — | Supabase 鉴权 |

---

## Gemma 4 — 四个在用角色

Gemma 4（默认 `gemma-4-26b-a4b-it-maas`）永远只用于*解读*或*给建议*——绝不计算评分或序列。每个角色都遵循同一形态：**纯函数库 → API 路由（鉴权 + Gemma + 安全解析）→ 组件**，模型不可用时优雅降级。

| # | 角色 | 时机 | 代码 | 输出 |
|---|---|---|---|---|
| 1 | **提交前 VCF 顾问** | 选文件后、提交前 | `src/lib/vcf-stats.ts` → `src/app/api/vcf-advisor/route.ts` → `VcfAdvisor.tsx` | 0–3 条结构化建议（JSON）。先做确定性 `CSQ` 检查，其余交给 Gemma。绝不阻塞。 |
| 2 | **多模态临床报告撰写** | 流水线内，评分/画图之后 | `pipeline/modules/gemma.py` | 400–600 字白话报告（读 JSON + 2 张 PNG）。 |
| 3 | **敏感性解说** | 按需，结果视图内 | `src/lib/sensitivity.ts` → `src/app/api/cases/[id]/sensitivity-narrate/route.ts` → `SensitivityPanel.tsx` | 1–2 句解说 what-if 阈值变化的得失。 |
| 4 | **对话助手** | 按需，结果视图内 | `src/app/api/cases/[id]/chat/route.ts` → `ChatWidget.tsx` | 围绕本病例候选 + 报告的自由问答。 |

角色 1–4 通过两套不同 SDK 访问同一个 Vertex AI 模型：**流水线内用 Python `google.genai`**（`gemma.py`），**Node API 路由用 `@google/genai`（`GoogleGenAI`）**。

---

## 数据模型

全部集中在一张表：`cases`（定义于 `supabase/migrations/20260508000001_cases.sql`）。

```
cases
├── id                         UUID 主键，gen_random_uuid()
├── created_at / updated_at    TIMESTAMPTZ
├── user_id                    UUID → auth.users，ON DELETE CASCADE   （NULL = 公开 demo 病例）
├── sample_name                TEXT
├── species                    TEXT  （默认 'canis_lupus_familiaris'）
├── alleles                    TEXT[]
├── predictors                 TEXT[] （默认 {NetMHCpan}）
├── status                     TEXT  CHECK IN ('pending','running','scoring',
│                                                        'reporting','designing','completed','failed')
│   ── 流水线产物（由 /progress 回调写入）──
├── candidates_json            JSONB
├── clinical_report_md         TEXT
├── mrna_fasta                 TEXT
├── mrna_summary_md            TEXT
├── binding_affinity_img_b64   TEXT   （base64 PNG）
├── mutation_landscape_img_b64 TEXT   （base64 PNG）
│   ── 汇总统计 ──
├── total_mutations            INTEGER
├── candidates_after_filtering INTEGER
└── error_message              TEXT
```

**行级安全**（两条策略）：

```sql
CREATE POLICY "users_own_cases" ON cases FOR ALL
  USING (auth.uid() = user_id);
CREATE POLICY "demo_cases_public" ON cases FOR SELECT
  USING (user_id IS NULL);
```

因此 API 路由对读操作无需手动按 `user_id` 过滤；`/progress` 回调是唯一以**管理员 service-role 客户端**写入的地方（绕过 RLS），前提是已通过共享密钥校验。

**设计说明**（承接 `docs/explainers/03-frontend-architecture.md`）：
- 图表以 **base64 存入 Postgres**（足够小），而非 GCS URL——若日后需要可一行代码切换。
- `candidates_json` 用 **JSONB**，因为它总是整体读取（从不按单个候选查询）。
- `status` 列是**唯一事实来源**，驱动客户端时间线（经 Realtime）。

---

## GCP 鉴权

`src/lib/gcp-auth.ts` → `getGcpAccessToken()` 为 Vercel 上的 API 返回 GCP 访问令牌，用于调用 GCS + Cloud Run Jobs。三条路径，按序尝试：

1. **`GOOGLE_APPLICATION_CREDENTIALS_JSON`** —— 服务账号密钥。这是**当前线上生效的路径**（短路掉其它两条），原因是 WIF 在黑客松时间窗内出现过可靠性问题。
2. **工作负载身份联合（WIF）** —— 用 STS 把 `VERCEL_OIDC_TOKEN` 换取联合令牌，再模拟 `rosie-pipeline-sa`。代码已正确接入（项目编号 `575738151193`，pool `vercel-pool`），目前是*预期*形态而非线上生效路径。
3. **应用默认凭据（ADC）** —— 本地开发兜底。

流水线（Cloud Run）以环境自带服务账号鉴权 GCP；它从 GCS 读 VCF、经回调写回结果——并不走 GCS 上传路径。

## 环境变量

| 变量 | 设置于 | 用途 |
|---|---|---|
| `GCS_BUCKET` | Vercel + Cloud Run | VCF 上传桶 |
| `GCP_PROJECT_ID` / `GCP_REGION` | Vercel + Cloud Run | GCP 项目 / 区域 |
| `CLOUD_RUN_JOB_NAME` | Vercel | Job 名（短名或完整资源路径） |
| `PIPELINE_CALLBACK_SECRET` | Vercel + Cloud Run | `/progress` 回调的共享密钥 |
| `NEXT_PUBLIC_APP_URL` | Vercel | 传入 Job 的回调基址 |
| `GEMMA_MODEL` | Vercel + Cloud Run | Vertex AI 模型 id（默认 `gemma-4-26b-a4b-it-maas`） |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | Vercel | 服务账号密钥（线上生效鉴权） |
| `VERCEL_OIDC_TOKEN` | 自动（Vercel） | WIF 路径所用 OIDC 令牌 |
| `CASE_ID`、`GCS_VCF_PATH`、`SAMPLE_NAME`、`ALLELES`、`SPECIES`、`GCS_TSV_PATH`、`SKIP_PREDICTION` | 由 Jobs API 每次注入 | `run_cloud.py` 的单次运行配置 |

## Demo 病例

`scripts/seed_demo.py`（以及 `pipeline/scripts/{build_demo.py,wipe_and_seed_demo.py}`）种入一个**公开 demo 病例**（`user_id IS NULL`），驱动 `/demo`。由于 RLS 有 `demo_cases_public`、且聊天/敏感性路由按 `user_id IS NULL` 分支，demo 无需账号即可完整体验。

## 旧文档中的陈旧点（本文已修正）

- **`docs/explainers/01-...`（第 8、9 步）** 称 Gemma 报告与 mRNA 设计"尚未构建"。两者均已上线：`pipeline/modules/gemma.py` 与 `pipeline/modules/mrna_design.py`。
- **`docs/explainers/04-cloud-deployment.md`** 把 `GET /api/upload-url`（resumable）描述为线上上传路径。提交页实际调用的是 `POST /api/upload`（经 Next.js 中转的 multipart）。两条路由都存在；线上生效的是 `/api/upload`。
- `README.md` 的"四个角色"叙述与数据模型与本文一致。

## 下一步（第 2 阶段，见 `README.md`）

FASTQ 摄入（BWA-MEM2 + GATK Mutect2）、MHC-II、peptide-MHC 结构预测（如 AlphaFold）、PyClone-VI 克隆性、Nextflow 编排、结构感知的密码子优化（LinearDesign），以及多构体初免/加强（prime/boost）剂量设计。

## 交叉引用

- `docs/explainers/01-from-dna-to-vaccine-candidates.md` —— 白话生物学走查 + 术语表
- `docs/explainers/02-key-decisions.md` —— 关键设计取舍的理由
- `docs/explainers/03-frontend-architecture.md` —— 前端、数据模型、顾问组件接线
- `docs/explainers/04-cloud-deployment.md` —— GCS、Cloud Run Jobs、WIF、回调
- `docs/hackathon-writeup.md` —— Gemma4Good 提交叙述
- `README.md` —— 产品概览与四个 Gemma 角色


# 构建
docker build -t rosie-web .

# 运行（注入必要的环境变量）
docker run -d -p 3000:3000 \
  -e NEXT_PUBLIC_SUPABASE_URL=... \
  -e NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=... \
  -e SUPABASE_SERVICE_ROLE_KEY=... \
  -e GCP_PROJECT_ID=... \
  -e GCS_BUCKET=... \
  -e PIPELINE_CALLBACK_SECRET=... \
  -e CLOUD_RUN_JOB_NAME=... \
  rosie-web