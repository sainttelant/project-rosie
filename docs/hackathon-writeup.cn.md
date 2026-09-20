
Project Rosie：为犬类打造个性化癌症疫苗

Gemma4Good · Health & Sciences 赛道 · Kaggle 黑客松项目介绍

面向肿瘤科医生的 AI 临床助手，从兽医医疗开始。它可以在数小时内将肿瘤 DNA 转化为可直接用于合成的 mRNA 疫苗，而 Gemma 4 则充当智能层，提供普通兽医诊所几乎不可能自行配备的专业能力。

问题是什么？

2025 年底，一位来自澳大利亚的 AI 创业者，同时也是一位拥有 17 年机器学习经验的资深从业者，为了给自己的狗狗 Rosie 设计一款个性化新抗原癌症疫苗，在一所大学研究实验室里花了整整三个月，基本依靠手工完成整个过程。

如果一个拥有这样技术背景的人都需要付出如此大的成本，那么对于一个没有机器学习经验的兽医肿瘤科医生来说，“能否使用这项技术”甚至都不能称之为一个问题，而是一堵墙。

个性化新抗原疫苗（personalized neoantigen vaccine）是目前最有前景的新兴癌症治疗方向之一。

然而，从已经完成测序的肿瘤样本，到最终生成可以真正合成的 mRNA 构建体，整个设计流程要求使用者熟悉：

pVACtools
NetMHCpan
密码子优化（codon optimization）
IVT 体外转录化学
以及至少五六种其他专业工具

普通兽医诊所不可能配备这样的人才。

所以，即使今天已经有一些犬类患者理论上可能从这种疫苗中获益，它们依然无法真正获得这种治疗。

Project Rosie 要做的，就是拆掉这堵墙。

它是一款 面向肿瘤科医生的 AI 临床助手（AI Clinical Assistant for Oncologists）。项目首先应用于兽医医疗，同时拥有一条可以直接延伸到人类肿瘤学的转化路径。

兽医只需要上传一份肿瘤变异检测文件（VCF），系统就会在云端运行整个分析流程：

耗时不到 1 小时
每个病例的云计算成本约 15 美元

最终，Dashboard 会自动生成四项结果：

按优先级排序的个性化新抗原候选靶点 20个
可直接用于合成的多表位 mRNA 构建体（FASTA）
供兽医肿瘤科医生阅读的通俗临床报告
可以直接发送给合同生产商的正式 mRNA 合成规格说明

项目地址：

Live：rosie.kiraklabs.com
Public Demo：rosie.kiraklabs.com/demo
Kaggle：原文所附 Kaggle writeup 链接
系统架构
层级	技术前端 + API	Next.js 16（App Router），部署于 Vercel
身份认证、数据库、实时通信	Supabase（Postgres + RLS + Realtime）
文件存储	Google Cloud Storage
Pipeline 运行环境	Python on Cloud Run Jobs（8 GiB、4 CPU、3 小时超时）
变异注释	Ensembl VEP（犬类 ROS_Cfam_1.0 cache）
新抗原预测	pVACtools + NetMHCpan via IEDB
候选打分	透明的 Python 综合评分算法，约 50 行代码
mRNA 设计	Biopython + 犬类密码子表
合成规格说明	Jinja 模板，刻意不使用 LLM 生成，原因见下文
LLM 层	Gemma 4（gemma-4-26b-a4b-it-maas），通过 Vertex AI 调用

整个 Pipeline 是一个确定性的 Python 脚本，每执行一个阶段都会通过 HTTP Callback 返回状态。

Next.js 前端通过 Supabase Realtime 订阅病例数据行的变化。

因此 UI 中的垂直时间线可以实时更新动画状态，完全不需要轮询（polling）。

我们是如何使用 Gemma 4 的

Rosie 并不是一个“先做传统 Pipeline，然后在最后硬塞一个 LLM”的项目。

下面的四个 Gemma 角色共同构成了一个真正的临床助手架构：

在 Pipeline 运行之前提供建议
在 Pipeline 完成之后解释结果
根据医生的临床判断进行交互式分析
随时以自然语言回答病例相关问题

它们共同为兽医肿瘤科医生提供了一种此前几乎从未拥有过的能力：

围绕一个完整病例提供专家级 AI 推理能力。

我们刻意让 Gemma 4 承担那些确定性 Pipeline 真正无法完成的工作。

也就是说，Gemma 的价值并不只是 Pipeline 运行结束以后“帮忙写点东西”，而是参与 Pipeline 之前以及周围的临床推理过程。

角色 1：运行前 VCF 顾问

Pre-flight VCF Advisor，主动式

当兽医上传一个 VCF 文件时，浏览器会首先解析其中的一些结构性信息，例如：

Variant 数量
INFO key
Sample columns
是否存在 somatic flag
染色体信息
FILTER 状态

随后把这些信息发送给 Gemma。

Gemma 会在真正启动计算任务之前，识别出 0～3 个可能降低预测质量的问题。

这样，用户就不会在存在明显数据质量问题的情况下，白白浪费一个小时的计算资源。

Gemma 使用严格的 JSON 格式返回结果，并提供安全解析 fallback。

它永远不会阻止用户提交任务。

例如：

“这份 VCF 中既没有 SOMATIC 标记，也没有 NORMAL 样本列。它看起来可能混合了胚系变异和体细胞变异。这会导致候选数量被非肿瘤突变人为放大。建议在提交之前，使用配对正常样本（matched-normal）的体细胞突变检测工具重新运行。”

角色 2：多模态临床报告生成器

Multimodal Clinical Report Writer，反应式

Pipeline 执行完成后，Gemma 会同时读取：

候选新抗原 JSON
结合亲和力柱状图 PNG
突变分布饼图 PNG

也就是说，这里使用了 Gemma 的多模态能力。

然后 Gemma 会撰写一份约 400～600 字的通俗临床报告。

系统 Prompt 还会根据不同物种自动切换：

DLA
HLA
FLA

等术语，并根据不同物种调整对于 IC50 数值的解释方式。

角色 3：敏感性分析解释器

Sensitivity Narrator，交互式

候选抗原表格下方提供了一个：

“What if?”（如果……会怎样？）

分析面板。

用户可以调整两个滑块：

IC50 threshold
Tumor VAF threshold

随着用户拖动滑块，哪些候选被保留、哪些候选被淘汰，以及相应排名都会立即在客户端重新计算。

这里不会每移动一次滑块就调用 Gemma，因此：

响应是即时的
Gemma API 成本为零

只有当用户点击：

“Ask Gemma to interpret”

Gemma 才会真正介入，对当前参数选择造成的临床权衡写出一段解释。

例如：

“提高结合亲和力和等位基因频率阈值的严格程度后，TP53 候选会被过滤掉，只剩下 PIK3CA 肽作为可行靶点。这会缩小新抗原候选池，同时导致最终疫苗构建体失去关键的 TP53 覆盖。”

这样一来，报告不再是一份静态文档。

兽医可以根据自己的临床判断去主动“询问”数据。

角色 4：对话式病例助手

Conversational Case Assistant，反应式

报告页面上有一个悬浮式 Chat Widget。

系统会把完整病例上下文加载进 System Prompt，包括：

样本信息
排名最高的候选抗原
已生成的临床报告

因此医生可以在数秒内通过自然语言对病例进行问答。

我们刻意没有让 Gemma 做什么

mRNA 合成规格说明（synthesis specification）最终会被原封不动发送给 CMO 合同生产商，例如：

TriLink
GenScript
Aldevron

最开始，我们其实让 Gemma 来生成这份文件。

后来把它替换成了确定性的 Jinja 模板。

为什么？

如果一个制剂科学家看到一个 AI 幻觉出来的产品目录编号、一个发生漂移的 QC 阈值，或者类似“请咨询您的生物信息学专家”这样的模糊措辞，他很可能直接对整个工具失去信任。

这个文档里面所有应该发生变化的信息，都来自患者和具体病例数据。

而制造科学本身是固定的，例如 CleanCap® AG cap1 / TriLink Cat# N-7413、100% m1Ψ 替代、SM-102 LNP 50:10:38.5:1.5 摩尔比、RIN ≥ 8.0 的放行标准等等。

这种场景应该使用模板，而不是生成式 AI。

因此，我们形成了这样一条原则：

AI 负责解释，确定性代码负责合规。

AI for interpretation, deterministic code for compliance.

这也是未来面对监管机构时，让整个工具具备可辩护性的关键。

底层 Pipeline 科学过程：

可复现
可审计

Gemma 则作为其上的解释层。

关键技术决策
决策	选择	原因输入格式	VCF，而不是 FASTQ	将 Phase 1 的搭建复杂度降低约 60%；FASTQ 导入作为 Phase 2，并明确计算了市场覆盖率从约 5% → 80%
合成规格	Jinja 模板，而非 LLM	CMO 订单文档必须是确定性的
Pipeline 编排	Python + Cloud Run Jobs	更适合 Hackathon Demo；生产版本计划迁移到 Nextflow
克隆性	使用 VAF 作为代理指标	Phase 2 将使用 PyClone-VI；Hackathon 阶段使用 VAF 是合理近似
AlphaFold	Phase 1 排除	排名准确度大约只能提升 5～10%，却需要每个病例消耗数小时 GPU，当前 ROI 不合理
敏感性重新排序	客户端过滤	滑块即时反馈，而且 Gemma 成本为零；只在用户明确要求解释的时候调用 Gemma

我们解决的难题
1. 多物种感知的多模态 Grounding

开箱即用的 Gemma 容易默认采用人类肿瘤学的表达框架。

因此项目在 System Prompt 模板中增加了物种切换机制：

自动切换 DLA / HLA / FLA 等术语
调整不同物种下 IC50 的解释阈值
确保生成的是兽医学语境，而不是默认套用人类医学表达
2. 不使用轮询的实时 Pipeline 状态

Cloud Run Jobs 每完成一个阶段都会发送一个 Callback：

Case Queued
 → Neoantigen Prediction
 → Candidate Ranking
 → Report Generation
 → mRNA Vaccine Design
 → Results Ready

Supabase Realtime 将状态变化直接推送到 React 组件树中。

因此，前端的垂直时间线可以实现实时动画更新，完全不需要 Polling。

3. Demo 数据质量

最初的犬类 Pipeline 运行结果只有一个高置信度候选抗原。

这会导致可视化非常无聊：

柱状图只有一根柱子
饼图就是一个完整的圆

因此，我们围绕合成 VCF 所针对的同样五个致癌驱动基因：

PIK3CA
TP53
BRCA2
KIT
PTEN

制作了一份更丰富的合成 Demo 数据，并重新生成可视化内容。

这样既让 Demo 更有展示效果，同时没有破坏犬类癌症这一项目叙事的真实性和一致性。

目前仍然缺失什么？

这是我们刻意保留的诚实章节。

1. 早期领域专家验证仍然不足

来自 Case Comprehensive Cancer Center 的一位 Senior Research Associate，拥有生物信息学及统计遗传学背景，对 Pipeline 进行了评审。

其评价是：

这是一个可信的 MVP，并且拥有真正有意义的发展潜力。

目前，我们正在推进来自 OVC Guelph / OICR 等比较肿瘤学团队更深入的临床验证。

2. Phase 1 从 VCF 开始

大多数兽医诊所最终从测序合作方获得的是 FASTQ。

因此加入：

FASTQ → VCF
 BWA-MEM2 + Mutect2

将成为 Phase 2 最大的产品采用率提升因素。

预计可使潜在可覆盖兽医诊所市场：

约 5% → 约 80%

但代价是：

计算成本约增加 16 倍
存储成本约增加 100 倍

这些内容已经记录在 README 中。

3. Tumor-only 样本处理

我们优先推荐：

Matched-normal calling

即同时利用肿瘤样本和匹配的正常样本进行变异检测。

如果只有肿瘤样本，那么整个 ranking 流程需要引入一个明确的置信度折扣机制。

现有的 Pre-flight Advisor 已经会识别并提醒这种情况。

Phase 2 将进一步把这种信息真正纳入候选抗原排名计算。

为什么这个项目的意义远超一次 Hackathon？

狗与人类共享很多重要的癌症驱动基因，例如：

TP53
PIK3CA
BRCA2
以及许多其他致癌驱动基因

犬类临床试验比人类临床试验更快，而且成本更低。

因此，从科学研究角度来看：

每一个通过这个 Pipeline 处理的犬类病例，都可以成为比较肿瘤学意义上的临床前研究数据。

为狗建立的方法论，有可能最终成为服务于人类患者的方法论。

由于 Gemma 4 是一个开放权重模型（open-weights model），诊所可以选择在自己的本地基础设施上部署 LLM 层。

也就是说：

患者的测序数据完全可以不离开医疗机构。

正因为如此，这个项目才有可能成为一个真正的：

开源产品，而不仅仅是一项 SaaS 服务。

这就是 Gemma4Good 在现实中的样子

它不是一个概念验证式的聊天机器人。

而是：

一个真实的医疗工作流
面向真实患者，首先是四条腿的患者
开放代码
工程设计具备可辩护性
同时对当前能力边界保持足够坦诚

Gemma 4 在这里扮演的是：

确定性 Pipeline 周围的“思考伙伴”，而不是 Pipeline 最后负责写几段漂亮文字的工具。

最能概括 Rosie 的定位是：

面向肿瘤科医生的 AI 临床助手，从那些无法为自己发声的患者开始。

确定性 Pipeline 负责生物学过程：

可复现、可审计，并遵循公开的阈值标准。

Gemma 负责：

理解、解释与交互。

这种职责划分，也使得当未来真正需要面对监管机构时，整个系统能够拥有更清晰、更具可辩护性的技术边界。

项目信息

赛道： Health & Sciences
 代码仓库： github.com/shashank-padala/project-rosie
 在线 Demo： rosie.kiraklabs.com/demo

翻译说明

我保留了 VCF、VAF、IC50、FASTQ、matched-normal、Pipeline、Grounding、CMO 等专业术语，因为这些词在生物信息学、机器学习和药物开发语境下直接使用英文通常更准确。同时对核心概念补充了中文解释，使这版翻译既适合技术人员阅读，也比较适合用于项目分享或内部评审。