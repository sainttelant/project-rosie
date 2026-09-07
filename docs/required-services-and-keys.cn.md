# 完整运行 Project Rosie — 所需服务、大模型与密钥清单

*面向"我要把这个工程完整跑起来"的读者。本文列出端到端运行（Web 前端 + 生信流水线 + 大模型）需要申请/开通的每一项外部服务、需要申请的大模型访问，以及每一个必须配置的环境变量/密钥。按"谁在用、用在哪、怎么申请"组织。*

> 一句话总览：**3 个外部平台（Supabase、Google Cloud、Vertex AI/Gemma 4）+ 1 个可选的 IEDB 公共 API**。大模型只有一个——**Gemma 4**（通过 Vertex AI 调用）。其余全是确定性代码。

---

## 一、总览：需要申请什么

| # | 服务 / 资源 | 提供方 | 用途 | 是否必须 | 计费 |
|---|---|---|---|---|---|
| 1 | Supabase 项目 | Supabase (Cloud) | 用户鉴权、病例数据库、Realtime 实时推送 | ✅ 必须 | 免费额度内可跑演示 |
| 2 | GCP 项目 | Google Cloud | 统一承载下面 3–7 项 | ✅ 必须 | 按用量 |
| 3 | Cloud Storage (GCS) 存储桶 | GCP | 存放用户上传的 VCF 文件 | ✅ 必须 | 按存储/请求 |
| 4 | Cloud Run Jobs | GCP | 运行生信流水线（pVACtools 等） | ✅ 必须 | 按 CPU/内存时长 |
| 5 | Vertex AI（Gemma 4 端点） | GCP | 调用大模型 Gemma 4 | ✅ 必须 | 按 token |
| 6 | Artifact Registry | GCP | 存放流水线 Docker 镜像 | ✅ 必须（上云时） | 按存储 |
| 7 | 服务账号 `rosie-pipeline-sa` | GCP IAM | 流水线 + 前端调用 GCP API 的身份 | ✅ 必须 | 免费 |
| 8 | IEDB REST API | IEDB（公共） | NetMHCpan 结合亲和力预测 | ⚠️ 默认走它 | 免费公共 API |
| 9 | Vercel（可选） | Vercel | 部署 Next.js 前端 + WIF 鉴权 | ⬜ 可选（本地/Docker 可不用） | 免费额度内可跑 |

> 说明：如果你用 **Docker 本地跑**（见 `README.md` 的 Docker 章节），则**不需要 Vercel**，前端和流水线都在本地容器里，GCP 鉴权走 `GOOGLE_APPLICATION_CREDENTIALS_JSON` 静态密钥即可。Vercel 只在"前端部署到云上 + 用 WIF 免密钥"时才需要。

---

## 二、大模型：只需要申请 Gemma 4

整个工程**只用到一个大模型：Gemma 4**（具体端点 `gemma-4-26b-a4b-it-maas`），通过 **Vertex AI** 调用。它承担 4 个角色（见 `README.md`）：

1. **预检 VCF 顾问**（提交前，主动）
2. **多模态临床报告撰写**（流水线后，被动）
3. **敏感性解说**（交互，按需）
4. **对话式病例助手**（报告页聊天）

### 如何申请 / 开通

- **方式 A（本项目采用）：Vertex AI 托管端点。** 在 GCP 控制台开通 **Vertex AI API**，并确认目标区域可用 `gemma-4-26b-a4b-it-maas` 这个 MaaS 端点。代码里通过 `google-genai` SDK 的 `genai.Client(vertexai=True, project=..., location=...)` 调用（见 `pipeline/modules/gemma.py:91`）。
- **方式 B（本地/私有化）：Gemma 4 是开放权重模型**，可下载权重在本地 GPU 上用 vLLM / TGI 等推理框架自托管，把 `GEMMA_MODEL` 指向你的端点即可。这也是 README 强调的"诊所可本地运行、患者数据不出大楼"的卖点。

### 大模型相关的环境变量

| 变量 | 必填 | 说明 |
|---|---|---|
| `GEMMA_MODEL` | — | 模型 ID，默认 `gemma-4-26b-a4b-it-maas`。自托管时改成你的端点/模型名 |
| `GCP_PROJECT_ID` | ✅ | Vertex AI 所在 GCP 项目 |
| `GCP_REGION` | — | Vertex AI 区域，默认 `us-central1` |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | ✅* | 服务账号 JSON 密钥，用于 Vertex AI 鉴权（*或用 WIF 的 `VERCEL_OIDC_TOKEN`） |

> 注意：调用 Gemma 4 的鉴权**复用 GCP 服务账号**（`roles/aiplatform.user`），不需要单独的 API key。

---

## 三、Supabase（鉴权 + 数据库 + 实时）

### 需要申请 / 创建

1. 一个 **Supabase 项目**（Cloud 或自托管 Postgres）。
2. 运行迁移建表：`supabase/migrations/20260508000001_cases.sql`（`cases` 表 + RLS 策略）。
3. 开启 **Supabase Auth**（邮箱/密码）。
4. 开启 **Realtime**（`cases` 表的变更推送）。

### 需要的 3 个密钥

| 变量 | 必填 | 说明 | 从哪拿 |
|---|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | ✅ | 项目 URL，如 `https://xxx.supabase.co` | Supabase 控制台 → Settings → API |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | ✅ | 公开（anon）key，前端用 | 同上 |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ | 服务角色 key，服务端写入、绕过 RLS | 同上（**仅服务端，切勿暴露到前端**） |

> `NEXT_PUBLIC_*` 两个会在**构建时**内联进前端 bundle（见 `README.md` Docker 章节的说明）。

---

## 四、Google Cloud（GCS + Cloud Run + Vertex AI + Artifact Registry）

### 需要开通的 GCP 服务

| 服务 | 用途 | 关键配置 |
|---|---|---|
| **Cloud Storage** | 存 VCF 上传 | 建桶 `project-rosie-pipeline`（`us-central1`），配 30 天生命周期（`scripts/gcs-lifecycle.json`） |
| **Cloud Run**（Jobs） | 跑流水线 | Job 名 `rosie-pipeline`；8Gi RAM / 4 CPU / 3h 超时 / 0 重试 |
| **Vertex AI** | 调 Gemma 4 | 见上文"大模型"节 |
| **Artifact Registry** | 存流水线镜像 | `us-central1-docker.pkg.dev/.../rosie-pipeline/pipeline:latest` |
| **IAM** | 服务账号 + 角色 | 见下 |

### 服务账号 `rosie-pipeline-sa` 需要的角色

| 角色 | 用途 |
|---|---|
| `roles/storage.objectAdmin` | 在 GCS 读写 VCF |
| `roles/run.developer` | 执行 Cloud Run Jobs |
| `roles/aiplatform.user` | 调用 Vertex AI 上的 Gemma 4 |
| `roles/iam.workloadIdentityUser` | 被 WIF 冒充（仅 Vercel 生产路径需要） |

### GCP 相关的环境变量

| 变量 | 必填 | 说明 |
|---|---|---|
| `GCP_PROJECT_ID` | ✅ | GCP 项目 ID（GCS + Cloud Run + Vertex AI 共用） |
| `GCP_REGION` | — | 区域，默认 `us-central1` |
| `GCS_BUCKET` | ✅ | VCF 上传的存储桶名 |
| `CLOUD_RUN_JOB_NAME` | ✅ | 要触发的 Cloud Run Job 名 |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | ✅* | 服务账号 JSON 密钥（*或用 WIF 的 `VERCEL_OIDC_TOKEN`） |
| `NEXT_PUBLIC_APP_URL` | — | 公网基础 URL，作为回调地址传给流水线 Job |

> **鉴权两条路径**（见 `src/lib/gcp-auth.ts`）：
> - **静态密钥**（当前生产实际使用）：设 `GOOGLE_APPLICATION_CREDENTIALS_JSON`，最简单可靠。
> - **WIF 免密钥**（Vercel 生产）：Vercel 注入 `VERCEL_OIDC_TOKEN` → STS 交换 → 冒充 `rosie-pipeline-sa`。需要先在 GCP 建 Workload Identity Pool 并把 `https://oidc.vercel.com` 注册为可信颁发者。

---

## 五、流水线内部依赖（非"申请"，但需知道）

生信流水线（`pipeline/`）本身是确定性代码，依赖以下**开源工具/公共 API**，无需申请账号，但需要网络可达：

| 依赖 | 说明 | 备注 |
|---|---|---|
| **pVACtools / pVACseq** | 新抗原预测编排 | 已打包进基础镜像 `griffithlab/pvactools` |
| **NetMHCpan 4.2** | MHC/DLA 结合亲和力 | 默认走 **IEDB REST API**（公共，免费）；本地二进制更快但需另装 IEDB 工具包 |
| **Ensembl VEP** | 变异注释 | 需 CanFam4 (ROS_Cfam_1.0) 缓存（约 1.5GB，含参考 FASTA） |
| **Biopython** | mRNA 密码子优化 | Python 库 |
| **Jinja2** | 合成规格书模板 | Python 库，确定性输出 |

> **IEDB** 是唯一的"外部公共 API"依赖（NetMHCpan 预测）。免费、无需 key，但**需要出网**。若完全离线部署，需改用 NetMHCpan 本地二进制（见 `docs/explainers/02-key-decisions.md` 决策 2）。

---

## 六、回调安全

| 变量 | 必填 | 说明 |
|---|---|---|
| `PIPELINE_CALLBACK_SECRET` | ✅ | 流水线 → 前端 `/api/cases/[id]/progress` 回调的共享密钥。Cloud Run 以 `Authorization: Bearer {secret}` 发送，前端校验 |

> 这个 secret 需要**同时**配置在前端（Vercel/容器）和 Cloud Run Job 两侧，且保持一致。

---

## 七、完整环境变量清单（一张表）

| 变量 | 必填 | 归属平台 | 用途 |
|---|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | ✅ | Supabase | 项目 URL |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | ✅ | Supabase | 公开 key（前端） |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ | Supabase | 服务角色 key（仅服务端） |
| `GCP_PROJECT_ID` | ✅ | GCP | 项目 ID（GCS/Run/Vertex 共用） |
| `GCP_REGION` | — | GCP | 区域（默认 `us-central1`） |
| `GCS_BUCKET` | ✅ | GCP | VCF 上传桶 |
| `CLOUD_RUN_JOB_NAME` | ✅ | GCP | 流水线 Job 名 |
| `GEMMA_MODEL` | — | Vertex AI | 模型 ID（默认 `gemma-4-26b-a4b-it-maas`） |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | ✅* | GCP | 服务账号 JSON 密钥（*或 WIF） |
| `VERCEL_OIDC_TOKEN` | —（Vercel 自动注入） | Vercel+GCP | WIF 鉴权（仅 Vercel 生产路径） |
| `PIPELINE_CALLBACK_SECRET` | ✅ | 前端+Cloud Run | 回调共享密钥 |
| `NEXT_PUBLIC_APP_URL` | — | 前端 | 公网基础 URL（回调 origin） |

---

## 八、最小可运行组合（按场景）

### 场景 A：本地 Docker 全栈（最快上手）
需要：**Supabase 项目（3 个 key）+ 一个 GCP 项目（GCS 桶 + Cloud Run Job + Vertex AI + 服务账号 JSON key）+ `PIPELINE_CALLBACK_SECRET`**。
不需要：Vercel、WIF。
```bash
# 前端
docker run -d -p 3000:3000 \
  -e NEXT_PUBLIC_SUPABASE_URL=... -e NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=... \
  -e SUPABASE_SERVICE_ROLE_KEY=... -e GCP_PROJECT_ID=... -e GCS_BUCKET=... \
  -e CLOUD_RUN_JOB_NAME=... -e PIPELINE_CALLBACK_SECRET=... \
  -e GOOGLE_APPLICATION_CREDENTIALS_JSON='...' rosie-web
# 流水线（推送到 Artifact Registry 后部署为 Cloud Run Job）
cd pipeline && docker build -t rosie-pipeline .
```

### 场景 B：生产（Vercel + WIF 免密钥）
在场景 A 基础上，把前端部署到 Vercel，配置 Workload Identity Pool，用 `VERCEL_OIDC_TOKEN` 替代 `GOOGLE_APPLICATION_CREDENTIALS_JSON`。

### 场景 C：完全离线 / 数据不出内网
- Gemma 4 改**自托管**（开放权重 + vLLM/TGI），`GEMMA_MODEL` 指向本地端点。
- NetMHCpan 改**本地二进制**（避免 IEDB 出网）。
- Supabase 可**自托管**（Postgres + GoTrue + Realtime）。
- 此时唯一仍需外部的是 GCS/Cloud Run——也可换成自建对象存储 + 自建容器编排。

---

## 九、申请顺序建议（Checklist）

1. ☐ 创建 **Supabase 项目** → 跑迁移 → 开 Auth + Realtime → 记下 3 个 key
2. ☐ 创建 **GCP 项目** → 开通 Cloud Storage / Cloud Run / Vertex AI / Artifact Registry
3. ☐ 建 **GCS 桶** + 30 天生命周期规则
4. ☐ 建 **服务账号** `rosie-pipeline-sa` + 4 个角色 → 导出 JSON key
5. ☐ 确认 **Vertex AI** 目标区域可用 `gemma-4-26b-a4b-it-maas`
6. ☐ 构建并推送 **流水线镜像** 到 Artifact Registry → 部署为 **Cloud Run Job**
7. ☐ 生成 **`PIPELINE_CALLBACK_SECRET`**，两侧配置一致
8. ☐ 前端注入全部环境变量 → 启动 → `curl http://localhost:3000/api/health` 验证
9. ☐ （可选）Vercel 部署 + WIF 配置

---

*相关文档：[`README.md`](../README.md)（Docker 构建与运行）、[`04-cloud-deployment.md`](./04-cloud-deployment.md)（云部署细节）、[`02-key-decisions.md`](./02-key-decisions.md)（NetMHCpan/IEDB 决策）。*
