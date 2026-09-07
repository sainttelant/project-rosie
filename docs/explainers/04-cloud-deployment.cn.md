# 云部署架构 — M5

*写给不熟悉 GCP 的工程师。无需生物学背景。*

---

## M5 解决的问题

M4 之后，提交表单在 Supabase 中创建了一个病例记录，但什么也没发生。VCF 文件从未被上传。没有流水线运行。病例永远停在"pending"。M5 接上完整路径：浏览器 → 云存储 → 计算 → 数据库 → 浏览器。

---

## 当兽医提交一个 VCF 时发生什么

```
1. 浏览器调用 GET /api/upload-url
   → Next.js API 调用 GCS 生成一个可恢复上传 URI
   → 把 URI 返回给浏览器

2. 浏览器用该 URI 直接把 VCF 文件 PUT 到 GCS
   → 中间没有 Next.js（避免大小限制，更快）
   → VCF 落在 gs://project-rosie-pipeline/vcf/{user}/{timestamp}/{file}

3. 浏览器用 GCS 路径调用 POST /api/cases
   → Next.js 插入一个病例行（status: "running"）
   → Next.js 调用 Cloud Run Jobs API 启动一个流水线作业
   → 返回病例 ID，浏览器导航到 /cases/{id}

4. Cloud Run Job 启动（异步）
   → 从 GCS 下载 VCF 到 /tmp
   → 运行 5 步流水线
   → 每个阶段之后 POST 到 /api/cases/{id}/progress

5. /api/cases/{id}/progress（回调端点）
   → 校验共享密钥
   → 更新 Supabase 中的病例行（status、部分结果）

6. 浏览器 /cases/{id}
   → Supabase Realtime 订阅检测到行更新
   → UI 用新状态重新渲染——无轮询、无刷新
   → 当 status = "completed" 时，完整报告出现
```

---

## 基础设施组件

### GCS 存储桶 — `project-rosie-pipeline`

位于 `us-central1` 的 Cloud Storage 存储桶。用于一件事：存储用户上传的 VCF 文件。结果（临床报告、mRNA、图表）直接以文本/base64 形式进入 Supabase——它们足够小。VCF 可能高达数百 MB，所以 GCS 是合适的地方。

30 天生命周期规则自动删除文件。流水线工作文件无需持久化。

### Cloud Run Job — `rosie-pipeline`

Cloud Run Jobs 是批处理工作负载——它们运行到完成然后关闭。不是长期运行的服务器。当 Next.js API 调用 Cloud Run Jobs REST API 时，GCP 从流水线镜像启动一个容器，运行 `run_cloud.py`，完成后终止。

配置为：
- 8Gi RAM — pVACseq 在表位评分期间内存消耗大
- 4 CPU — 预测是 CPU 密集型
- 3 小时超时 — 足以处理突变众多的大型犬类 VCF
- 0 最大重试 — 流水线失败应当暴露，而非静默重试

### Docker 镜像

流水线容器位于 Artifact Registry 的 `us-central1-docker.pkg.dev/project-1ea30ea7-dc79-4a14-84b/rosie-pipeline/pipeline:latest`。

基于 `griffithlab/pvactools:latest` 构建（预装 pVACtools + VEP + NetMHCpan）。在其之上：`requirements.txt` 依赖（google-cloud-storage、google-genai、matplotlib、biopython）+ 流水线模块 + 以 `run_cloud.py` 作为入口点。

### `pipeline/run_cloud.py`

Cloud Run 入口点。所有配置都通过 Cloud Run Jobs API 在执行时注入的环境变量传入（病例 ID、GCS 路径、等位基因、回调 URL 等）。

它做什么：
1. 从 GCS 下载 VCF 到 `/tmp`
2. 调用 `/api/cases/{id}/progress`，带 `status: "running"`
3. 运行每个流水线阶段，每个阶段之后调用 progress
4. 最终回调发送 `status: "completed"` 及所有结果（base64 PNG、markdown 报告、mRNA FASTA、候选 JSON）

阶段 → 状态映射：
| 阶段 | 发送的状态 |
|---|---|
| 作业启动 | `running` |
| 评分完成 | `scoring` |
| 可视化完成 | `reporting` |
| mRNA 设计完成 | `designing` |
| 全部完成 | `completed` |

### 工作负载身份联合（WIF）

> **状态说明：** WIF 已接线，下面的代码路径是正确的，但**生产环境当前使用的是 `src/lib/gcp-auth.ts` 中的静态密钥回退**（`GOOGLE_APPLICATION_CREDENTIALS_JSON` 环境变量在 Vercel 上设置，短路了 WIF 路径）。WIF 路径在黑客松时间线内遇到了可靠性问题，所以部署回退到了服务账号密钥。下面的文本描述的是代码中实现的 WIF 设计；把它当作预期的生产姿态，而非当前激活的那个。

Vercel 上的 Next.js API 需要调用 GCP API（Cloud Run Jobs、GCS）。通常你会用一个服务账号 JSON 密钥。但 GCP 项目有一条组织策略阻止密钥创建（`constraints/iam.disableServiceAccountKeyCreation`）。

WIF 无需密钥即可解决：
1. Vercel 为每个请求生成一个短期 OIDC token（`VERCEL_OIDC_TOKEN`）
2. Next.js 代码用它与 GCP 的 Security Token Service（STS）交换一个联合 token
3. 那个联合 token 冒充 `rosie-pipeline-sa` 服务账号
4. 得到的访问 token 用于所有 GCP API 调用

信任关系：Vercel 的 OIDC 颁发者（`https://oidc.vercel.com`）被注册为 Workload Identity Pool 中的可信颁发者。GCP 只向匹配所配置属性条件的 Vercel OIDC token 颁发 token。

服务账号 `rosie-pipeline-sa` 拥有：
- `roles/storage.objectAdmin` — 在 GCS 中读写 VCF
- `roles/run.developer` — 执行 Cloud Run Jobs
- `roles/aiplatform.user` — 在 Vertex AI 上调用 Gemma 4
- `roles/iam.workloadIdentityUser` — 通过 WIF 被冒充

### 回调鉴权

流水线（运行在 Cloud Run 中）回调 Next.js API 以更新病例状态。互联网上任何人都能调用那个端点。为防止伪造回调，双方共享 `PIPELINE_CALLBACK_SECRET`。Cloud Run 把它作为 `Authorization: Bearer {secret}` 发送。Next.js 路由拒绝任何不匹配的内容。

### Supabase Realtime

`/cases/[id]` 页面订阅 `cases` 表上过滤到当前病例 ID 的 Postgres 变更。当流水线回调更新该行时，Supabase 通过 WebSocket 把变更推送给所有订阅者。浏览器重新获取完整行并重新渲染——无轮询间隔、无页面刷新。

---

## 环境变量

| 变量 | 设置于 | 用途 |
|---|---|---|
| `GCS_BUCKET` | Vercel | VCF 上传的存储桶名 |
| `GCP_PROJECT_ID` | Vercel + Cloud Run | GCP 项目 |
| `CLOUD_RUN_JOB_NAME` | Vercel | Jobs API 的完整作业资源名 |
| `PIPELINE_CALLBACK_SECRET` | Vercel + Cloud Run | 回调鉴权的共享密钥 |
| `NEXT_PUBLIC_APP_URL` | Vercel | Vercel 部署 URL——传给 Cloud Run 让它知道回调到哪里 |
| `VERCEL_OIDC_TOKEN` | Vercel 自动注入 | 用于 WIF 鉴权的 OIDC token |
| `CASE_ID`、`GCS_VCF_PATH`、`ALLELES` 等 | Cloud Run Jobs API 每次运行注入 | 每作业配置 |

---

## 关键文件

| 文件 | 用途 |
|---|---|
| `pipeline/run_cloud.py` | Cloud Run Job 入口点 |
| `pipeline/Dockerfile` | 容器定义 |
| `src/lib/gcp-auth.ts` | WIF token 交换助手 |
| `src/app/api/upload-url/route.ts` | 生成 GCS 可恢复上传 URI |
| `src/app/api/cases/route.ts` | 创建病例 + 触发 Cloud Run Job |
| `src/app/api/cases/[id]/progress/route.ts` | 接收流水线阶段回调 |
| `src/app/cases/[id]/page.tsx` | 带 Realtime 订阅的客户端组件 |
| `scripts/gcs-lifecycle.json` | GCS 30 天自动删除生命周期规则 |
