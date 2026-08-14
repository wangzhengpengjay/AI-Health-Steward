# 本地 AI 健康管家 - 项目总览

> 本文档是项目的导航入口，说明文件架构、每份文件的作用、当前进度和下一步。
> 最后更新：2026-08-14（V1.2 完成，V1.3 新功能方向探索中）

---

## 一、项目定位

| 维度 | 说明 |
|------|------|
| 产品形态 | 本地私有化部署的家庭 AI 健康管家，开源项目（MIT） |
| 第一用户 | 本人 + 家庭，单实例服务一个家庭 |
| 模型策略 | API 为主（多模态必选、文字可选），兼容本地 LLM（Ollama） |
| 主界面 | WebUI 承载完整管理（画像/报告/体检/设置） |
| 渠道扩展 | 飞书为轻咨询 + 资料收集主入口，后续邮件等 |
| 产品定位 | **双入口协同**：WebUI=完整后台（深度管理），飞书=轻入口（随手用），数据自动回流共享 |
| 项目定位 | 完全独立的开源项目，无第三方代码/数据复用 |

---

## 二、技术栈（已确定）

| 层 | 选型 | 决策依据 |
|---|------|---------|
| 后端 | Python 3.12 + FastAPI | AI/LLM 生态碾压级优势（design.md TD1） |
| 前端 | React 18 + Vite + TypeScript + TailwindCSS | MediUI Design Token 映射 |
| 数据库 | PostgreSQL 16 + pgvector | 单库事务一致性，结构化+向量一体化（TD2） |
| ORM | SQLAlchemy 2.0 + Alembic | 异步支持，2.0 Mapped 语法 |
| AI 模型 | OpenAI 兼容 API + Ollama | function calling 一体化路由（TD4） |
| 部署 | Docker Compose | 一键启动，pgvector 镜像 |

---

## 三、文件架构

```
ai-native/
├── OVERVIEW.md                              ← 你正在看的这份文档
├── README.md                                ← 项目 README（特性/快速开始/技术栈/路线）
├── LICENSE                                  ← MIT
├── .env.example                             ← 环境变量模板
├── .gitignore
├── docker-compose.yml                       ← 一键部署（Postgres+pgvector + 后端 + 前端）
│
├── backend/                                 ← Python FastAPI 后端
│   ├── Dockerfile
│   ├── requirements.txt                     ← 依赖清单
│   ├── alembic.ini                          ← Alembic 配置
│   ├── alembic/
│   │   └── env.py                           ← 迁移环境（导入所有 model）
│   ├── app/
│   │   ├── main.py                          ← FastAPI 入口 + CORS + /health
│   │   ├── core/
│   │   │   ├── config.py                    ← Pydantic Settings（读 .env，含鉴权/限流/报告目录）
│   │   │   ├── database.py                  ← SQLAlchemy 异步引擎 + session
│   │   │   ├── security.py                  ← Bearer Token 鉴权 + 滑动窗口限流（P0-3）
│   │   │   └── reference_ranges.py          ← 成人/儿童参考范围 + 临床危急值阈值（P0-2/P1-2）
│   │   ├── models/
│   │   │   ├── family.py                    ← A 字段族：FamilyMember 表（含长期记忆字段）
│   │   │   └── health.py                    ← B-H 字段族：健康画像表 + 报告/向量/消息表
│   │   ├── schemas/
│   │   │   ├── family.py                    ← 成员 Pydantic schema
│   │   │   └── health.py                    ← 指标 Pydantic schema（自动计算异常/危急值）
│   │   ├── api/
│   │   │   ├── v1/router.py                 ← 路由汇总（挂载全局鉴权）
│   │   │   └── routes/
│   │   │       ├── members.py               ← 家庭成员 CRUD API（含软删除）
│   │   │       ├── metrics.py               ← 指标录入 API（按年龄分档参考范围）
│   │   │       ├── chat.py                  ← AI 咨询（非流式 + SSE 流式）
│   │   │       ├── reports.py               ← 报告上传/确认/状态机
│   │   │       ├── feishu.py                ← 飞书渠道管理
│   │   │       ├── checkup.py               ← 体检推荐
│   │   │       ├── profile.py               ← 健康画像 CRUD
│   │   │       └── settings.py              ← 模型配置/数据导出/清除
│   │   ├── services/                        ← 业务逻辑
│   │   │   ├── consultation.py              ← AI 咨询编排（工具调用/风险分级/记忆注入）
│   │   │   ├── member_memory.py             ← 长期会话记忆（增量压缩）
│   │   │   ├── checkup_recommend.py         ← 1+X+Y 体检推荐
│   │   │   ├── feishu.py                    ← 飞书渠道接入
│   │   │   ├── extractor.py                 ← 指标抽取（V0.3 前方案，已弃用，保留备查）
│   │   │   └── tools/                       ← 6 个健康工具（extract_and_save/query_*）
│   │   └── providers/                       ← 模型 provider 抽象（多模态/文字/本地）
│   └── tests/
│       ├── test_health.py                   ← 健康检查测试
│       ├── test_reference_ranges.py         ← 参考范围/危急值单测
│       ├── test_security.py                 ← 鉴权/限流单测
│       └── test_consultation.py             ← 风险分级单测
│
├── frontend/                                ← React 前端
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.ts                       ← Vite + 代理 /api → :8000
│   ├── tailwind.config.ts                   ← MediUI Design Token 映射
│   ├── tsconfig.json                        ← strict 模式
│   ├── index.html                           ← HTML 入口（Material Symbols）
│   └── src/
│       ├── main.tsx                         ← React 入口 + QueryClient + Router
│       ├── App.tsx                          ← 路由定义（默认 /home）
│       ├── index.css                        ← TailwindCSS + MediUI CSS 变量
│       ├── types/index.ts                   ← TypeScript 类型（A-H 字段族）
│       ├── lib/api.ts                       ← fetch 封装 + 各业务 api
│       ├── stores/memberStore.ts            ← Zustand（当前成员 + 成员列表）
│       ├── components/
│       │   ├── Layout.tsx                   ← 页面布局壳层（全局拉取成员）
│       │   ├── Sidebar.tsx                  ← 侧边栏导航
│       │   └── MemberSwitcher.tsx           ← 成员切换器
│       └── pages/
│           ├── Home.tsx                     ← 家庭健康速览（默认首页）
│           ├── Dashboard.tsx                ← 画像看板（含危急值红色预警）
│           ├── Chat.tsx                     ← AI 咨询（SSE 流式 + 图片解读）
│           ├── Reports.tsx                  ← 报告管理（上传/确认/入档）
│           ├── CheckupRecommend.tsx         ← 体检推荐（1+X+Y）
│           ├── Members.tsx                  ← 成员管理（✅ 完整实现）
│           ├── MetricInput.tsx              ← 手动录入（✅ 完整实现）
│           └── Settings.tsx                 ← 设置（模型配置/导出/清除）
│
└── openspec/                                ← 需求文档与架构设计
    ├── config.yaml                          ← OpenSpec 配置
    └── changes/ai-health-steward/
        ├── proposal.md                      ← 需求概述 + 用户故事 + 成功指标
        ├── design.md                        ← 10 架构决策(D1-D10) + 5 技术决策(TD1-TD5) + 风险
        ├── tasks.md                         ← V0.1-V1.0 共 5 版 35 个任务
        ├── specs/                           ← 6 个 capability 详细规格
        │   ├── health-profile/spec.md       ← 成员管理/字段族/入档/溯源/数据权利
        │   ├── report-ingestion/spec.md     ← 上传/路由/抽取/归属/状态机/异常处理
        │   ├── ai-consultation/spec.md      ← 意图路由/六类意图/工具调用/风险分级/预警
        │   ├── visualization/spec.md        ← 趋势图/异常标识/画像看板
        │   ├── channels/spec.md             ← WebUI/飞书/适配层/异常处理/身份识别
        │   └── model-provider/spec.md       ← 三类 provider/必选依赖/路由逻辑
        ├── UI-DESIGN-SYSTEM.md              ← UI 设计系统（Token/原子组件/组合组件/页面适配）
        ├── PRD-REVIEW.md                    ← 第一轮 PRD 评审报告
        └── PRD-REVIEW-R2.md                 ← 第二轮 PRD 评审报告（通过）
```

---

## 四、文档说明

### 4.1 规划层（OpenSpec artifacts）

| 文件 | 作用 | 什么时候看 |
|------|------|-----------|
| `proposal.md` | 需求的「为什么」和「做什么」。含用户故事、成功指标、6 个 capability 边界 | 回顾"我们到底要做什么"时 |
| `design.md` | 架构决策（D1-D10）+ 技术选型（TD1-TD5）+ 风险 + 非功能需求 | 做架构或技术评审时 |
| `tasks.md` | V0.1 到 V1.0 五个版本，35 个可勾选任务 | 跟踪开发进度时 |
| `specs/*/spec.md` | 每个 capability 的 SHALL/SHOULD 需求 + WHEN/THEN 场景 | 开发某个功能前看对应 spec |
| `UI-DESIGN-SYSTEM.md` | MediUI Design Token + 原子组件 + 组合组件 + 页面适配 + 交互闭环 | 开发 UI 时对照看 |
| `PRD-REVIEW.md` | 第一轮评审（5 阻塞性问题 + 7 建议性问题） | 了解修复历史 |
| `PRD-REVIEW-R2.md` | 第二轮评审（全部通过，3 个不阻塞残留） | 确认 PRD 质量 |

### 4.2 代码层

| 目录 | 当前状态 | 说明 |
|------|---------|------|
| `backend/app/core/` | ✅ 完成 | 配置 + 数据库 + 鉴权限流 + 参考范围/危急值 |
| `backend/app/models/` | ✅ 完成 | 健康画像表 + 报告/向量/消息表（含长期记忆字段） |
| `backend/app/schemas/` | ✅ 完成 | 成员 + 指标 + 各类 schema |
| `backend/app/api/routes/` | ✅ 完成 | 成员/指标/咨询/报告/飞书/体检/画像/设置 |
| `backend/app/providers/` | ✅ 完成 | 多模态/文字/本地 provider 抽象 + 路由 |
| `backend/app/services/` | ✅ 完成 | 咨询编排/记忆/体检推荐/飞书/工具集 |
| `backend/app/services/tools/` | ✅ 完成 | 6 个健康工具（extract_and_save/query_*） |
| `backend/tests/` | ✅ 基础 | 健康检查 + 参考范围/安全/风险分级单测 |
| `frontend/src/pages/` | ✅ 完成 | 家庭速览/画像/咨询/报告/体检/成员/录入/设置 |
| `frontend/src/components/` | ✅ 完成 | Layout + Sidebar + MemberSwitcher + 报告组件 |

---

## 五、版本规划与进度

```
V0.1 核心骨架 ✅     V0.2 AI 咨询 ✅      V0.3 报告+可视化 ✅  V0.4 飞书 ✅       V1.0 开源+加固 ✅
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   ┌──────────────┐
│ 项目脚手架 ✅  │    │ 意图路由 ✅   │    │ 图片上传 ✅  │    │ 渠道适配 ✅   │   │ 部署文档 ✅   │
│ 模型层抽象 ✅ │───▶│ 工具调用 ✅   │───▶│ 多模态抽取 ✅│───▶│ 飞书Bot接入 ✅│──▶│ 隐私声明 ✅   │
│ 画像数据模型 ✅│    │ 六类意图 ✅   │    │ 趋势图 ✅    │    │ 资料收集 ✅   │   │ 示例数据 ✅   │
│ 家庭成员管理 ✅│    │ 聊天抽取 ✅   │    │ 报告状态机 ✅│    │ 轻问答 ✅     │   │ 开发者文档 ✅ │
│ 手动录入 ✅   │    │ 风险分级 ✅   │    │ RAG 检索 ✅ │    │              │   │ 鉴权限流     │
│ WebUI ✅     │    │ 对话界面 ✅   │    │ 体检推荐 ✅  │    │              │   │ 年龄分档/危急 │
│              │    │ 多模态输入 ✅ │    │ 画像看板 ✅  │    │              │   │ 速览/长期记忆 │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘   └──────────────┘
  能存能看 ✅          能聊 ✅             能看趋势 ✅       能随手丢 ✅        能fork能跑 ✅
```

### V0.1 任务进度 — 全部完成 ✅

| 任务 | 状态 | 说明 |
|------|------|------|
| 1.1 初始化项目结构 | ✅ | 目录/README/LICENSE/.env/docker-compose |
| 1.2 技术栈脚手架 | ✅ | FastAPI + React + TailwindCSS |
| 1.3-1.6 model-provider | ✅ | 三类 provider 抽象 + 路由逻辑 + 状态 API |
| 1.7-1.8 数据模型 + 成员 CRUD | ✅ | 8 张表 + 成员 API（含软删除） |
| 1.9 手动录入入档 | ✅ | 指标录入 API + 异常/危急值自动判定 |
| 1.10 WebUI 基础框架 | ✅ | 布局 + 成员管理页 + 指标可视化中心 |

### V0.2 任务进度 — 全部完成 ✅

| 任务 | 状态 | 说明 |
|------|------|------|
| 2.1-2.2 意图路由 + 工具框架 | ✅ | function calling 一体化 |
| 2.3-2.5 查询工具 | ✅ | query_metrics / query_profile / query_abnormal |
| 2.6-2.8 咨询意图 | ✅ | 指标解读/用药咨询/症状咨询（含免责声明） |
| 2.9 聊天抽取回填 | ✅ | extract_and_save 工具 + 用户确认 |
| 2.10 角色知识边界 | ✅ | S/A/B 风险分级 + 高危预警 |
| 2.11 WebUI 对话界面 | ✅ | SSE 流式 + Markdown 渲染 + ChatBubble |
| 2.12 多模态对话输入 | ✅ | 图片/PDF 上传 + 粘贴图片 |
| 2.13 全局成员加载 | ✅ | Layout 层统一拉取 |

### V0.3 任务进度 — 全部完成 ✅

| 任务 | 状态 | 说明 |
|------|------|------|
| 3.1-3.2 报告上传 + 抽取 | ✅ | AI 咨询页 + 指标页上传浮窗，多模态单次抽取 |
| 3.6-3.8 指标可视化 | ✅ | Tab切换 + 多线图 + 医学参考范围 + 定制备注 + BMI计算 |
| 3.3-3.5 结构化确认 + 归属 + 入档 | ✅ | JSON 确认面板 + 姓名识别 + 溯源 |
| 3.9 画像看板 | ✅ | Dashboard 页完整实现 |
| 3.10 向量化知识库 | ✅ | RAG 语义检索 |
| 3.11 报告状态机 | ✅ | 完整状态流转 + 重试/取消 |

### V0.4 任务进度 — 全部完成 ✅

| 任务 | 状态 | 说明 |
|------|------|------|
| 4.1 渠道适配抽象 | ✅ | 多渠道框架 |
| 4.2 飞书 Bot 接入 | ✅ | WebSocket 长连接 + 多 Bot |
| 4.3 资料收集 | ✅ | 图片报告解析 |
| 4.4 轻问答 | ✅ | 文字咨询 |

### V1.0 任务进度 — 开源发布 + 体验/安全加固

| 任务 | 状态 | 说明 |
|------|------|------|
| 5.1-5.3 开源发布 | ✅ | 文档/隐私/示例数据 |
| 优化 P0-1 | ✅ | 消除重复指标抽取 LLM 调用（成本） |
| 优化 P0-3 | ✅ | Bearer Token 鉴权 + 对话限流（安全） |
| 优化 P0-2 | ✅ | 成人/儿童分档参考范围（正确性） |
| 优化 P1-2 | ✅ | 临床危急值阈值 + 看板红色预警 |
| 优化 P1-1 | ✅ | 家庭健康速览首页 |
| 优化 P1-4 | ✅ | 长期会话记忆（增量压缩） |
| 优化 P1-3 | ✅ | 核心逻辑单元测试（29 项） |
| 优化 P2 | ✅ | 文档同步 + 产品定位 + 代码质量优化（见 V1.2） |

### 三大新功能（V1.1）— 全部完成 ✅

| 功能 | 状态 | 说明 |
|------|------|------|
| 复测/用药待办提醒 | ✅ | health_tasks 表 + 自动生成钩子（危急→立即复查、异常→30天复测、用药中→提醒、慢病→随访、体检→预约）+ 待办区块 |
| 健康小结/周期报告 | ✅ | health_summaries 表 + 规则/LLM 小结生成（周/月/年）+ /summaries 页面 |
| 风险自测量表 | ✅ | 9量表（PHQ-9/GAD-7/糖尿病/ASCVD/ISI/高血压/血脂/AD8/卒中）+ 计分分档 + 频控 + assess_scale 对话工具 + /assess 页面 |

### V1.2 代码质量与体验优化 — 全部完成 ✅

| 分类 | 项 | 状态 | 说明 |
|------|------|------|------|
| P0 | SSE 多模态调用卡住 | ✅ | fitz/Pillow 同步 C 库阻塞事件循环，asyncio.to_thread() 包装 |
| P0 | 提取事务长时间占用 | ✅ | extracting 状态 flush+commit 后释放，结果再 commit |
| P0 | JSON 解析无统一清洗 | ✅ | parse_model_json() 统一函数，处理 markdown 围栏/尾逗号/前后文字 |
| P1 | EXTRACT_PROMPT 三处重复 | ✅ | 统一到 app/prompts/__init__.py |
| P1 | _age/_metric_label 重复 | ✅ | 统一到 app/core/utils.py (compute_age + metric_label) |
| P1 | chat/chat_stream 逻辑重复 | ✅ | 提取 _prepare_turn() 共享方法 |
| P1 | _create_report_record 过重 | ✅ | 135行拆分为 6 个聚焦方法 |
| P1 | 死代码清理 | ✅ | 删除 PagePlaceholder.tsx + report_extract_v1.md |
| P2 | chat_history 分页 | ✅ | limit/before_id 参数，limit+1 检测 has_more |
| P2 | 前端展示 last_result | ✅ | ScaleCard 展示上次测评结果（分数+风险标签+日期） |
| P2 | UPLOAD_DIR 统一 | ✅ | config.py Settings 集中管理 |
| P2 | bare except 补日志 | ✅ | reports.py 静默吞 JSON 错误加 logger.warning |

---

## 六、PRD 评审状态

PRD 已通过两轮评审，达到可进入需求评审标准：

| 维度 | 第一轮 | 第二轮 |
|------|--------|--------|
| 完整性 | 待完善（5问题） | ✅ 通过 |
| 清晰度 | 待完善（4问题） | ✅ 通过 |
| 边界覆盖 | 待完善（7问题） | ✅ 通过（1残留） |
| 可度量性 | 待完善（4问题） | ✅ 通过 |
| 医疗合规 | 待完善（5问题） | ✅ 通过（1残留） |
| 工程可实施性 | 待完善（4问题） | ✅ 通过（1残留） |

3 个不阻塞残留：工具接口签名（技术评审定）、埋点事件清单（工程阶段补）、B/A 级边界升级规则（角色边界补）。

---

## 七、接下来要做什么

### 7.1 V1.0 开源收尾（已完成 ✅）

1. ~~P2 剩余项~~ — ✅ 代码质量优化已全部完成（V1.2）
2. **数据库迁移** — `alembic upgrade head` 应用最新迁移（含 i9d0e1f2a3b4 长期记忆字段）
3. **端到端联调** — Docker 三容器运行中，核心流程已验证
4. **发布收尾** — 生成示例数据、补充截图、确认 README_EN 同步

### 7.2 V1.3 新功能方向探索（进行中 🔍）

已完成 13 个方向的头脑风暴与行业调研，分为三组：

**主动服务方向（①-⑥）**：JITAI 智能随访、TTM 目标教练、报告解读推送、多信号风险预警、家庭健康协调者（⭐最高差异化）、健康决策中枢

**健康延伸方向（⑦-⑫）**：保险方案推荐、就医资源导航、数字疗法引擎、家庭照护协调、健康商城推荐、用药管理深化

**专业底座方向（⑬）**：循证医学知识引擎 — 让 AI 的每句话都有出处

> 详细调研与方向分析见 `openspec/changes/ai-health-steward/V1.3-DIRECTIONS.md`

### 7.3 原有建议后续方向（V1.3+）

- **数据趋势可视化深化**：多指标同图对比、历史报告对比、趋势预警线
- **用药管理页**：独立用药管理界面（目前只有数据表无前端页面）
- **成员画像详情页**：整合诊断/用药/过敏/家族史/生活方式的完整画像展示
- **自定义预警规则**：用户可配置指标阈值与提醒规则（目前硬编码在 reference_ranges.py）
- **移动端/飞书路径**：明确飞书为轻咨询主入口，WebUI 承载完整管理
- **多实例/权限细化**：从单家庭扩展到多家庭隔离与分角色权限

---

## 八、快速导航

| 我想... | 看哪里 |
|--------|--------|
| 回顾需求全貌 | `openspec/changes/ai-health-steward/proposal.md` |
| 理解架构决策 | `openspec/changes/ai-health-steward/design.md`（D1-D10 + TD1-TD5） |
| 看版本规划和任务 | `openspec/changes/ai-health-steward/tasks.md` |
| 看某个功能的详细需求 | `openspec/changes/ai-health-steward/specs/<capability>/spec.md` |
| 看 UI 设计规范 | `openspec/changes/ai-health-steward/UI-DESIGN-SYSTEM.md` |
| 看 PRD 评审结论 | `openspec/changes/ai-health-steward/PRD-REVIEW-R2.md` |
| 看 V1.3 方向探索 | `openspec/changes/ai-health-steward/V1.3-DIRECTIONS.md` |
| 看后端代码 | `backend/app/`（main.py 入口） |
| 看前端代码 | `frontend/src/`（App.tsx 路由入口） |
| 校验 OpenSpec 状态 | `cd ai-native && openspec validate ai-health-steward --json` |
| 启动开发环境 | `cp .env.example .env && docker-compose up -d` |
