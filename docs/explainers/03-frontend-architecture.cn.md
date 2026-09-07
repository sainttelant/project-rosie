# 前端架构 — M4 Web 应用

*写给不熟悉这里使用的 Next.js / Supabase 技术栈的工程师和产品人员。无需生物学背景。*

> **本文档首次撰写（M4）以来的更新：** 下文描述的若干桩（stub）已经交付。报告查看器现在是一个**垂直流水线时间线**（`src/components/PipelineTimeline.tsx`），而非最初计划的标签页视图。提交表单做**真实的 GCS 上传**到一个可恢复上传会话并触发 Cloud Run Jobs（不再有"文件名被丢弃"的桩）。Supabase Realtime 驱动实时状态。新增了一个 **Gemma 顾问层**（M4b）——见本文档底部附近的专门章节。仪表盘表格也重新设计了（每行操作见 `src/components/CaseDashboardActions.tsx`）。下面保留原始的 M4 叙述以供历史参考。

---

## M4 是什么

M4 是把流水线输出变成兽医肿瘤医生真正能用的东西的 Web 应用。生信流水线（M1–M3）产出 JSON 文件、PNG 图表、一份 markdown 报告和一段 FASTA 序列。M4 是浏览器界面，诊所在那里上传 VCF、观看流水线运行、阅读报告、下载 mRNA 序列，并向 Gemma 4 询问关于病例的问题。

---

## 数据模型

一切都存放在一张 Supabase 表里：`cases`。

```
cases
├── id                         UUID — 主键
├── user_id                    UUID — 引用 auth.users（公开演示病例为 NULL）
├── sample_name                TEXT — 例如 "BUDDY_TUMOR_01"
├── species                    TEXT — 例如 "canis_lupus_familiaris"
├── alleles                    TEXT[] — 预测所用的 MHC/DLA 等位基因
├── status                     TEXT — 流水线阶段: pending → running → scoring → reporting → designing → completed
│
│   流水线输出（M5 在 Cloud Run 完成时写入）:
├── candidates_json            JSONB — 完整排序候选列表（前 20 名带分数）
├── clinical_report_md         TEXT — Gemma 4 markdown 报告
├── mrna_fasta                 TEXT — 密码子优化的 mRNA 构体
├── mrna_summary_md            TEXT — 合成指导文档
├── binding_affinity_img_b64   TEXT — base64 编码的结合亲和力 PNG
├── mutation_landscape_img_b64 TEXT — base64 编码的突变谱 PNG
│
│   汇总统计:
├── total_mutations            INTEGER — 分析的突变总数
├── candidates_after_filtering INTEGER — 通过硬过滤的候选数
└── error_message              TEXT — 若 status = 'failed' 则设置
```

**为什么用 base64 图像而非 GCS URL？** 对于黑客松演示，我们把 PNG 直接以 base64 字符串形式存入数据库。这避免了为 M4 配置 GCS 签名 URL。M5 会把这些移到 Cloud Storage 并用 URL 替换这些列。`<Image>` 组件用一行改动即可处理两种模式。

**为什么候选用 JSONB？** 候选列表总是整体读取——我们从不查询单个候选。JSONB 提供无连接的快速读取，并让 TypeScript 直接反序列化为 `CandidatesJson`。

---

## 行级安全

Supabase 直接在 PostgreSQL 中强制行级安全（RLS）。两条策略：

```sql
-- 用户只能看到自己的病例
CREATE POLICY "users_own_cases" ON cases
  FOR ALL USING (auth.uid() = user_id);

-- 演示病例（user_id IS NULL）无需鉴权即可公开读取
CREATE POLICY "demo_cases_public" ON cases
  FOR SELECT USING (user_id IS NULL);
```

这意味着 API 路由无需手动按 `user_id` 过滤——数据库会拒绝任何读取他人病例的尝试。一个未登录用户可以读取演示病例，但不能读取任何人的私有病例。

种子脚本（`scripts/seed_demo.py`）以 `user_id = NULL` 插入 HCC1395 基准病例。`/demo` 页面无需鉴权即可获取它。

---

## 路由结构

```
/                    落地页 — 公开
/demo                演示报告查看器 — 公开（从 Supabase 加载 user_id=NULL 病例）
/auth/login          登录表单 — 公开
/auth/signup         注册表单 — 公开
/dashboard           病例列表 — 需要鉴权
/submit              新建病例表单 — 需要鉴权（3 步向导）
/cases/[id]          完整报告查看器 — 需要鉴权，校验 user_id 匹配

/api/cases           GET: 列出用户病例   POST: 创建新病例
/api/cases/[id]      GET: 单个病例（鉴权门控）
/api/cases/[id]/chat POST: 带病例上下文的 Gemma 4 聊天（演示病例无需鉴权即可访问）
```

鉴权保护在每个页面服务端用 `supabase.auth.getUser()` 完成。若未鉴权，页面重定向到 `/auth/login?next=<path>`。

---

## 报告查看器

`ReportViewer` 是核心组件。它接收一个完整的 `Case` 行并渲染四个标签页：

| 标签页 | 内容 | 展示什么 |
|---|---|---|
| 临床报告 | Markdown → HTML | Gemma 4 的白话分析：候选推理、临床上下文、建议的下一步 |
| 候选 | 可排序表格 | 排名、肽序列、基因、肽长度、等位基因、IC50（颜色编码）、VAF、综合分数 |
| mRNA 设计 | FASTA 查看器 + 设计摘要 | 带复制和下载按钮的密码子优化 mRNA 构体；下方是合成参数 |
| 图表 | 两张 PNG 图像 | 结合亲和力柱状图（前 20 IC50 值）和突变谱饼图 |

如果病例状态不是 `completed`，查看器显示流水线进度时间线而非标签页。每个阶段都列出，当前阶段高亮——一旦 M5 接上 Supabase Realtime，这会实时动画。

**候选表中的 IC50 颜色编码：**
- 绿色（< 50 nM）：强结合者——临床上有意义
- 黄色（50–150 nM）：中等结合者——值得考虑
- 灰色（> 150 nM）：弱结合者——进入前 20 但被降权

---

## Gemma 4 聊天组件

浮动"询问 Gemma 4"按钮出现在任何已完成的病例（演示或私有）上。打开时：

1. 用户输入问题并按回车
2. 调用 `POST /api/cases/[id]/chat`，带上消息和对话历史
3. API 路由从 Supabase 加载病例，构建一个系统提示，包含：
   - 前 5 个候选摘要（肽、基因、IC50、分数）
   - 临床报告的前 800 个字符
4. 消息 + 历史被发送到 Vertex AI 全局端点上的 `gemma-4-26b-a4b-it-maas`
5. 响应流式返回并出现在聊天面板中

聊天在服务端是无状态的——每次请求都发送完整历史。这对黑客松规模没问题（对话很短），也避免了需要一个独立的对话存储层。

**为什么只加载临床报告的 800 字符？** 完整报告可能有 3,000–5,000 字符。在每一轮聊天中都包含全部会消耗大部分上下文预算。800 字符的截断覆盖了执行摘要和关键发现，能回答大多数问题。对于关于特定章节的深入问题，用户可以滚动到相关标签页并更具体地提问。

---

## 提交表单

三步，每步一个屏幕：

1. **患者信息** — 样本名（必填）、物种下拉（狗/人/猫）
2. **等位基因** — 带常见等位基因组预设按钮的文本输入（人类 MHC-I 常见；犬类 DLA 常见）。逗号分隔。
3. **VCF 上传 + 审阅** — 拖放区，提交前显示一个摘要卡片

提交时调用 `POST /api/cases`。API 在 Supabase 创建一行，`status: pending`，并返回 `id`。页面重定向到 `/cases/[id]`，显示流水线进度视图。

**注意**：VCF 上传到 GCS 在 M5 接线。对于 M4，VCF 文件名被接受后丢弃。病例注册为 `pending` 并停留在那里，直到 M5 加入 Cloud Run 触发。

---

## 设计系统

应用始终是深色——没有浅色模式切换。Tailwind v4 带自定义 OKLCH token：

| Token | 值 | 用途 |
|---|---|---|
| `--background` | `oklch(0.10 0.01 240)` | 页面背景——深海军蓝黑 |
| `--card` | `oklch(0.14 0.01 240)` | 卡片和面板——比背景略亮 |
| `--primary` | `oklch(0.75 0.15 175)` | 青色强调——链接、CTA、IC50 高亮、状态指示 |
| `--muted-foreground` | `oklch(0.60 0.01 220)` | 次要文本——描述、元数据 |
| `--border` | `oklch(1 0 0 / 8%)` | 细微边框——8% 白色不透明度 |

青色强调（`--primary`）在 sRGB 中约为 #00c9a7。它被选来感觉干净、临床，而不带纯白底黑字的生硬感。

---

## M5 会为此添加什么

M5 会接上 M4 留作桩的部分：

- **VCF → GCS 上传**：用真实的 Cloud Storage 文件上传替换 `/submit` 中仅文件名的桩，返回一个 GCS URI
- **Cloud Run 触发**：插入病例行后，`POST /trigger` 到 FastAPI 桥服务以启动流水线作业
- **实时状态**：在 `/cases/[id]` 页面订阅 Supabase 的 `cases` 通道——来自 Cloud Run 回调的状态更新实时出现，无需页面刷新
- **GCS URL 图像**：用签名 GCS URL 替换 base64 PNG 列，更新 `ReportViewer` 使用 `src={caseData.binding_affinity_url}` 而非 base64 data URI

---

## Gemma 顾问组件（M4b — 已交付）

在 M4 基础上新增了两个 Gemma 驱动的组件——它们是项目超越"流水线末尾的 LLM 报告撰写者"的主要差异化。见 `docs/explainers/02-key-decisions.md` 决策 9 了解理由；本节覆盖前端接线。

### `<VcfAdvisor>` — 预检 VCF 检查

挂载在提交页（`src/app/(app)/submit/page.tsx`）第 3 步内，位于拖放区和审阅摘要卡片之间。

| 文件 | 用途 |
|---|---|
| `src/lib/vcf-stats.ts` | 纯浏览器端 VCF 解析器。读取文件前 5 MB，提取变异数、INFO 键、样本列（TUMOR/NORMAL 检测）、体细胞标志是否存在、看到的染色体、FILTER 值、fileformat 头、参考头。从不抛异常。 |
| `src/components/VcfAdvisor.tsx` | UI。监听 `file` prop；变化时客户端解析统计，然后 POST 到 `/api/vcf-advisor`。渲染加载药丸（"Gemma 正在审阅你的 VCF…"），然后 0–3 条类型化建议注释（info / warning / critical），或一个"✓ VCF 看起来干净"的勾。 |
| `src/app/api/vcf-advisor/route.ts` | 服务端端点。鉴权门控（已登录用户）。用严格 JSON 提示把结构事实发送给 `gemma-4-26b-a4b-it-maas`；安全解析响应；返回 `{ notes: AdvisoryNote[] }`。Gemma 失败时降级为 `{ notes: [] }`——从不阻塞提交。 |

**UX 形态：** 文件选择时自动运行（每个文件一次 Gemma 调用）。加载状态行内，从不弹窗。无论顾问结果如何，提交始终可用。

### `<SensitivityPanel>` — what-if 阈值探索器

挂载在 `src/components/PipelineTimeline.tsx` 中，紧跟 `<CandidatesArtifact>` 之后，用于 `candidates_json` 已填充的病例。在 `/cases/[id]`（已登录用户病例）和 `/demo`（公开演示病例）上都可见。

| 文件 | 用途 |
|---|---|
| `src/lib/sensitivity.ts` | 纯客户端重排序。`applySensitivity(candidates, thresholds)` 基于 IC50 和 VAF 截止值返回 `{ kept, dropped }`。默认值镜像 `pipeline/modules/scoring.py:12-13`（`HARD_FILTER_IC50=500`、`HARD_FILTER_VAF=0.01`）。 |
| `src/components/SensitivityPanel.tsx` | UI。可折叠卡片，带两个范围输入（IC50 对数刻度 50→1000 nM，VAF 线性 0.01→0.50）。实时计数行在滑块拖动时即时更新——在用户点击"让 Gemma 解读"之前没有 Gemma 调用。 |
| `src/app/api/cases/[id]/sensitivity-narrate/route.ts` | 服务端端点。鉴权门控，与聊天路由相同的双模式（已登录用户或演示的 `user_id IS NULL`）。把阈值 + 保留/剔除列表发送给 Gemma；返回 `{ narrative: string }`。 |

**UX 形态：** 零 LLM 成本的即时滑块反馈。解说仅在用户明确要求时生成——保持 Vertex AI 配额使用有界。

### 添加更多顾问功能时要复制的模式

两个组件遵循相同的形态：
1. **纯 lib**（`src/lib/*.ts`）——做结构化工作（解析或过滤），零副作用。
2. **API 路由**（`src/app/api/.../route.ts`）——鉴权门控 + Gemma 调用 + 安全解析回退。
3. **组件**（`src/components/*.tsx`）——把 lib 接到路由接到 UI；Gemma 失败时优雅降级。

这种分离让 Gemma 的角色被清晰地约束（仅解读），并让底层逻辑无需 LLM 参与即可审计。
