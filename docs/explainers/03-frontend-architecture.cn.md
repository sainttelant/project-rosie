前端架构 —— M4 Web 应用

写给不熟悉本项目所用 Next.js / Supabase 技术栈的工程师与产品同学。无需生物学背景。

自本文档首次撰写以来的更新（M4）： 下文描述的若干占位实现已经落地。报告查看器现在是纵向流水线时间轴（src/components/PipelineTimeline.tsx），而非最初计划的分页签视图。提交表单已完成真实的 GCS 上传，上传到可断点续传的上传会话，并触发 Cloud Run Jobs（不再是"文件名被丢弃"的占位实现）。Supabase Realtime 驱动实时状态更新。新增了一层 Gemma 顾问（M4b）—— 详见本文末尾的专门章节。仪表盘表格也经过了重新设计（逐行操作见 src/components/CaseDashboardActions.tsx）。下方 M4 的原始叙述予以保留，作为历史背景。

M4 是什么

M4 是一个 Web 应用，负责把流水线的产出变成兽医肿瘤学家真正能用的东西。生物信息学流水线（M1–M3）产出 JSON 文件、PNG 图表、一份 markdown 报告和一条 FASTA 序列。M4 则是浏览器端的界面：诊所在这里上传 VCF、观察流水线运行、阅读报告、下载 mRNA 序列，并向 Gemma 4 提出关于该病例的问题。

数据模型

所有内容都存放在 Supabase 的一张表里：cases。
├── id                         UUID — 主键
├── user_id                    UUID — 关联 auth.users（公开演示病例为 NULL）
├── sample_name                TEXT — 例如 "BUDDY_TUMOR_01"
├── species                    TEXT — 例如 "canis_lupus_familiaris"
├── alleles                    TEXT[] — 预测中使用的 MHC/DLA 等位基因
├── status                     TEXT — 流水线阶段：pending → running → scoring → reporting → designing → completed
│
│   流水线产出（由 M5 在 Cloud Run 完成时写入）：
├── candidates_json            JSONB — 完整排序候选列表（含分数的前 20 名）
├── clinical_report_md         TEXT — Gemma 4 生成的 markdown 报告
├── mrna_fasta                 TEXT — 经密码子优化的 mRNA 构建体
├── mrna_summary_md            TEXT — 合成指导文档
├── binding_affinity_img_b64   TEXT — base64 编码的结合亲和力 PNG
├── mutation_landscape_img_b64 TEXT — base64 编码的突变图谱 PNG
│
│   汇总统计：
├── total_mutations            INTEGER — 已分析的突变总数
├── candidates_after_filtering INTEGER — 通过硬过滤的候选数
└── error_message              TEXT — 当 status = 'failed' 时写入


为什么用 base64 图片而不是 GCS URL？ 对于黑客松演示，我们把 PNG 直接以 base64 字符串存进数据库，这样就免去了为 M4 配置 GCS 签名 URL 的麻烦。M5 会把这些图片迁移到 Cloud Storage，并用 URL 替换这两列。<Image> 组件只需改一行就能同时兼容两种模式。

为什么候选列表用 JSONB？ 候选列表总是被整体读取——我们从不单独查询某一条候选。JSONB 读取快、无需 join，并且能让 TypeScript 直接反序列化为 CandidatesJson。

行级安全

Supabase 直接在 PostgreSQL 中强制实施行级安全（RLS）。共两条策略：
-- 用户只能看到自己的病例
CREATE POLICY "users_own_cases" ON cases
  FOR ALL USING (auth.uid() = user_id);

-- 演示病例（user_id IS NULL）无需登录即可公开读取
CREATE POLICY "demo_cases_public" ON cases
  FOR SELECT USING (user_id IS NULL);


这意味着 API 路由无需手动按 user_id 过滤——数据库会直接拒绝任何读取他人病例的尝试。未登录用户可以读取演示病例，但无法读取任何人的私有病例。

种子脚本（scripts/seed_demo.py）会以 user_id = NULL 插入 HCC1395 基准病例。/demo 页面无需鉴权即可获取它。

路由结构


/                    落地页 —— 公开
/demo                演示报告查看器 —— 公开（从 Supabase 加载 user_id=NULL 的病例）
/auth/login          登录表单 —— 公开
/auth/signup         注册表单 —— 公开
/dashboard           病例列表 —— 需登录
/submit              新建病例表单 —— 需登录（3 步向导）
/cases/[id]          完整报告查看器 —— 需登录，并校验 user_id 匹配

/api/cases           GET：列出用户病例    POST：创建新病例
/api/cases/[id]      GET：单个病例（鉴权保护）
/api/cases/[id]/chat POST：带病例上下文的 Gemma 4 对话（演示病例无需登录即可访问）


鉴权保护在每个页面服务端通过 supabase.auth.getUser() 完成。若未认证，页面会重定向到 /auth/login?next=<path>。

报告查看器

ReportViewer 是核心组件。它接收完整的一行 Case 数据，并渲染四个页签：

页签 内容 展示什么

临床报告 Markdown → HTML Gemma 4 的通俗语言分析：候选推理、临床背景、推荐的后续步骤

候选列表 可排序表格 排名、肽段序列、基因、肽段长度、等位基因、IC50（带颜色编码）、VAF、综合分数

mRNA 设计 FASTA 查看器 + 设计摘要 经密码子优化的 mRNA 构建体，带复制与下载按钮；下方为合成参数

图表 两张 PNG 图片 结合亲和力柱状图（前 20 名 IC50 值）与突变图谱饼图

如果病例状态不是 completed，查看器会显示流水线进度时间轴，而非页签。每个阶段都会列出，当前阶段高亮显示——等 M5 接上 Supabase Realtime 后，这里会实时动起来。

候选表格中的 IC50 颜色编码：
• 绿色（< 50 nM）：强结合 —— 具有临床意义

• 黄色（50–150 nM）：中等结合 —— 值得考虑

• 灰色（> 150 nM）：弱结合 —— 虽在前 20 名内，但优先级已降低

Gemma 4 对话组件

浮动的"Ask Gemma 4"按钮会出现在任何已完成的病例上（演示或私有均可）。打开后：

1. 用户输入问题并按下回车
2. 调用 POST /api/cases/[id]/chat，携带消息与对话历史
3. API 路由从 Supabase 加载病例，并构建包含以下内容的系统提示词：
   • 前 5 名候选摘要（肽段、基因、IC50、分数）

   • 临床报告的前 800 个字符

4. 消息 + 历史被发送到 Vertex AI global 端点上的 gemma-4-26b-a4b-it-maas
5. 响应以流式返回，并显示在对话面板中

对话在服务端是无状态的——每次请求都会发送完整历史。对于黑客松的量级这完全够用（对话本身很短），也省去了单独一层对话存储。

为什么只加载临床报告的 800 个字符？ 完整报告可能有 3,000–5,000 个字符。如果每一轮对话都把它完整带进去，多轮下来会吃掉大部分上下文预算。截取 800 个字符足以覆盖执行摘要与关键发现，能回答大多数问题。如果想深入问某个具体章节，用户可以滚动到相应页签后更有针对性地提问。

提交表单

三步，每步一屏：

1. 患者信息 —— 样本名（必填）、物种下拉框（狗/人/猫）
2. 等位基因 —— 文本输入框，附常见等位基因组合的预设按钮（Human MHC-I common；Canine DLA common）。以逗号分隔。
3. VCF 上传 + 确认 —— 拖拽放置区，提交前展示一张摘要卡片

提交时调用 POST /api/cases。API 在 Supabase 中创建一行记录，status 为 pending，并返回 id。页面跳转到 /cases/[id]，显示流水线进度视图。

注意：VCF 上传到 GCS 将在 M5 中接通。在 M4 中，VCF 文件名被接收后被丢弃。病例会登记为 pending，并一直保持该状态，直到 M5 加入 Cloud Run 触发逻辑。

设计系统

应用始终为深色——没有浅色模式开关。使用 Tailwind v4 与自定义 OKLCH 令牌：

令牌 值 用途

--background oklch(0.10 0.01 240) 页面背景 —— 深海军蓝黑

--card oklch(0.14 0.01 240) 卡片与面板 —— 比背景略亮

--primary oklch(0.75 0.15 175) 青绿色强调色 —— 链接、CTA、IC50 高亮、状态指示

--muted-foreground oklch(0.60 0.01 220) 次要文字 —— 描述、元数据

--border oklch(1 0 0 / 8%) 微妙的边框 —— 8% 白色不透明度

青绿色强调色（--primary）在 sRGB 下约为 #00c9a7。选择它是为了营造干净、临床化的观感，同时避免纯白配纯黑那种冷硬的刺眼感。

M5 将在此基础上补充什么

M5 会接通 M4 中留作占位的部分：

• VCF → GCS 上传：把 /submit 中"仅文件名"的占位实现，替换为真正上传文件到 Cloud Storage 并返回 GCS URI

• Cloud Run 触发：插入病例记录后，调用 FastAPI 桥接服务的 POST /trigger 来启动流水线作业

• 实时状态：在 /cases/[id] 页面订阅 Supabase 的 cases 频道——来自 Cloud Run 回调的状态更新会实时呈现，无需刷新页面

• GCS URL 图片：用带签名的 GCS URL 替换 base64 PNG 列，并把 ReportViewer 改为使用 src={caseData.binding_affinity_url} 而非 base64 data URI

Gemma 顾问组件（M4b —— 已上线）

在 M4 基础之上新增了两个由 Gemma 驱动的组件——它们构成了本项目区别于"把大模型当作流水线末端报告撰写器"的核心差异化点。设计理由参见 docs/explainers/02-key-decisions.md 决策 9；本节只覆盖前端接线部分。

<VcfAdvisor> —— 运行前 VCF 检查

挂载在提交页面（src/app/(app)/submit/page.tsx）的第 3 步中，位于拖拽放置区与确认摘要卡片之间。

文件 作用

src/lib/vcf-stats.ts 纯浏览器端 VCF 解析器。最多读取文件前 5 MB，提取变异数量、INFO 键、样本列（识别 TUMOR/NORMAL）、是否存在体细胞标记、出现的染色体、FILTER 取值、fileformat 头、reference 头。永不抛异常。

src/components/VcfAdvisor.tsx UI。监听 file prop；变化时先在客户端解析统计信息，再 POST 到 /api/vcf-advisor。渲染加载胶囊（"Gemma is reviewing your VCF…"），随后展示 0–3 条带类型的提示（info / warning / critical），或显示"✓ VCF looks clean"的通过标记。

src/app/api/vcf-advisor/route.ts 服务端端点。需鉴权（登录用户）。以严格 JSON 提示词把结构性事实发送给 gemma-4-26b-a4b-it-maas；对响应做安全解析；返回 { notes: AdvisoryNote[] }。Gemma 调用失败时降级为 { notes: [] } —— 从不阻塞提交。

交互形态： 选择文件后自动运行（每个文件一次 Gemma 调用）。加载态内联呈现，绝不用模态框。无论顾问结果如何，提交按钮始终可用。

<SensitivityPanel> —— 假设情景阈值探索器

挂载在 src/components/PipelineTimeline.tsx 中 <CandidatesArtifact> 之后，适用于 candidates_json 已填充的病例。在 /cases/[id]（登录用户病例）与 /demo（公开演示病例）上均可见。

文件 作用

src/lib/sensitivity.ts 纯客户端重新排序。applySensitivity(candidates, thresholds) 根据 IC50 与 VAF 阈值返回 { kept, dropped }。默认值与 pipeline/modules/scoring.py:12-13 保持一致（HARD_FILTER_IC50=500、HARD_FILTER_VAF=0.01）。

src/components/SensitivityPanel.tsx UI。可折叠卡片，内含两个 range 滑块（IC50 为对数刻度 50→1000 nM，VAF 为线性 0.01→0.50）。拖动滑块时实时计数行即时更新 —— 在用户点击"Ask Gemma to interpret"之前不产生任何 Gemma 调用。

src/app/api/cases/[id]/sensitivity-narrate/route.ts 服务端端点。鉴权采用与对话路由相同的双模式（登录用户，或演示病例的 user_id IS NULL）。把阈值与保留/剔除列表发送给 Gemma；返回 { narrative: string }。

交互形态： 滑块反馈即时响应、零大模型成本。解读文本仅在用户明确请求时生成 —— 使 Vertex AI 配额消耗保持在可控范围内。

新增更多顾问功能时可复用的模式

两个组件遵循相同的结构：
1. 纯函数库（src/lib/*.ts）—— 完成结构化工作（解析或过滤），无任何副作用。
2. API 路由（src/app/api/.../route.ts）—— 鉴权门禁 + Gemma 调用 + 安全解析降级。
3. 组件（src/components/*.tsx）—— 把 lib、路由与 UI 串起来；Gemma 失败时优雅降级。

这种分离让 Gemma 的角色边界保持清晰（仅做解读），并使底层逻辑在脱离大模型的情况下依然可审计。