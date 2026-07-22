# 本地 AI 健康管家 - 项目总览

> 本文档是项目的导航入口，说明文件架构、每份文件的作用、当前进度和下一步。
> 最后更新：2026-07-22（V0.2 完成）

---

## 一、项目定位

| 维度 | 说明 |
|------|------|
| 产品形态 | 本地私有化部署的家庭 AI 健康管家，开源项目（MIT） |
| 第一用户 | 本人 + 家庭，单实例服务一个家庭 |
| 模型策略 | API 为主（多模态必选、文字可选），兼容本地 LLM（Ollama） |
| 主界面 | WebUI 承载完整功能 |
| 渠道扩展 | 飞书（资料收集 + 轻问答），后续邮件等 |
| 与晓医关系 | 完全独立，无代码/数据复用，功能上部分重叠 |

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
│   │   │   ├── config.py                    ← Pydantic Settings（读 .env）
│   │   │   └── database.py                  ← SQLAlchemy 异步引擎 + session
│   │   ├── models/
│   │   │   ├── family.py                    ← A 字段族：FamilyMember 表
│   │   │   └── health.py                    ← B-H 字段族：7 张健康画像表
│   │   ├── schemas/
│   │   │   ├── family.py                    ← 成员 Pydantic schema
│   │   │   └── health.py                    ← 指标 Pydantic schema（自动计算异常/危急值）
│   │   ├── api/
│   │   │   ├── v1/router.py                 ← 路由汇总
│   │   │   └── routes/
│   │   │       ├── members.py               ← 家庭成员 CRUD API（含软删除）
│   │   │       └── metrics.py               ← 指标录入 API（手动录入+来源标记）
│   │   ├── services/                        ← 业务逻辑（待填充）
│   │   └── providers/                       ← 模型 provider 抽象（待填充）
│   └── tests/
│       └── test_health.py                   ← 健康检查测试
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
│       ├── App.tsx                          ← 路由定义（6 条路由）
│       ├── index.css                        ← TailwindCSS + MediUI CSS 变量
│       ├── types/index.ts                   ← TypeScript 类型（A-H 字段族）
│       ├── lib/api.ts                       ← fetch 封装 + membersApi + metricsApi
│       ├── stores/memberStore.ts            ← Zustand（当前成员 + 成员列表）
│       ├── components/
│       │   ├── Layout.tsx                   ← 页面布局壳层
│       │   ├── Sidebar.tsx                  ← 侧边栏导航
│       │   └── MemberSwitcher.tsx           ← 成员切换器
│       └── pages/
│           ├── Dashboard.tsx                ← 画像看板（占位，V0.3 完整实现）
│           ├── Chat.tsx                     ← AI 咨询（占位，V0.2 完整实现）
│           ├── Reports.tsx                  ← 报告管理（占位，V0.3 完整实现）
│           ├── Members.tsx                  ← 成员管理（✅ 完整实现）
│           ├── MetricInput.tsx              ← 手动录入（✅ 完整实现）
│           ├── Settings.tsx                 ← 设置（占位）
│           └── PagePlaceholder.tsx          ← 占位页共享骨架
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
| `backend/app/core/` | ✅ 完成 | 配置管理 + 数据库引擎 |
| `backend/app/models/` | ✅ 完成 | 8 张表（A-H 全字段族） |
| `backend/app/schemas/` | ✅ 完成 | 成员 + 指标的 Pydantic schema |
| `backend/app/api/routes/` | ✅ 完成 | 成员 CRUD + 指标录入 API |
| `backend/app/providers/` | 待实现 | 模型 provider 抽象（V0.1 1.3-1.6） |
| `backend/app/services/` | 待实现 | 业务逻辑层 |
| `frontend/src/pages/` | 部分完成 | Members + MetricInput 完整，其余占位 |
| `frontend/src/components/` | ✅ 基础完成 | Layout + Sidebar + MemberSwitcher |

---

## 五、版本规划与进度

```
V0.1 核心骨架 ✅     V0.2 AI 咨询 ✅      V0.3 报告+可视化      V0.4 飞书          V1.0 开源发布
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   ┌──────────────┐
│ 项目脚手架 ✅  │    │ 意图路由 ✅   │    │ 图片上传 ✅  │    │ 渠道适配抽象  │   │ 部署文档     │
│ 模型层抽象 ✅ │───▶│ 工具调用 ✅   │───▶│ 多模态抽取 ✅│───▶│ 飞书Bot接入  │──▶│ 隐私声明     │
│ 画像数据模型 ✅│    │ 六类意图 ✅   │    │ 趋势图 ✅    │    │ 资料收集     │   │ 示例数据     │
│ 家庭成员管理 ✅│    │ 聊天抽取 ✅   │    │ 医学参考范围✅│    │ 轻问答       │   │ 开发者文档   │
│ 手动录入 ✅   │    │ 风险分级 ✅   │    │ BMI计算 ✅  │    │              │   │ README       │
│ WebUI ✅     │    │ 对话界面 ✅   │    │ 画像看板     │    │              │   │              │
│              │    │ 多模态输入 ✅ │    │ 向量化知识库 │    │              │   │              │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘   └──────────────┘
  能存能看 ✅          能聊 ✅             能看趋势 (部分)     能随手丢            能fork能跑
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

### V0.3 任务进度 — 部分完成

| 任务 | 状态 | 说明 |
|------|------|------|
| 3.1-3.2 报告上传 + 抽取 | ✅ | AI 咨询页 + 指标页上传浮窗 |
| 3.6-3.8 指标可视化 | ✅ | Tab切换 + 多线图 + 医学参考范围 + 定制备注 + BMI计算 |
| 3.3-3.5 结构化确认 + 归属 + 入档 | 待实现 | JSON 确认面板 + 姓名识别 + 溯源 |
| 3.9 画像看板 | 待实现 | Dashboard 页完整实现 |
| 3.10 向量化知识库 | 待实现 | RAG 检索 |
| 3.11 报告状态机 | 待实现 | 完整状态流转 |

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

### 7.1 V0.1 剩余工作

1. **1.3-1.6 model-provider 能力** — 三类 provider 抽象接口（多模态 API / 文字 API / 本地 LLM）+ 输入类型路由逻辑
2. **数据库迁移** — `alembic revision --autogenerate` 生成首次迁移并执行
3. **端到端联调** — 启动 Postgres + 后端 + 前端，验证成员管理和指标录入全流程

### 7.2 V0.2 AI 咨询能力

4. 意图路由器（function calling 一体化）
5. 工具调用框架（query_metrics / query_profile 等工具定义）
6. 六类健康意图实现
7. 聊天抽取回填闭环
8. 角色知识边界 + S/A/B 风险分级 + 高危预警
9. WebUI 对话界面

### 7.3 后续版本

- V0.3：报告导入 + 可视化（多模态抽取、趋势图、画像看板）
- V0.4：飞书渠道
- V1.0：开源发布（文档、隐私声明、示例数据）

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
| 看后端代码 | `backend/app/`（main.py 入口） |
| 看前端代码 | `frontend/src/`（App.tsx 路由入口） |
| 校验 OpenSpec 状态 | `cd ai-native && openspec validate ai-health-steward --json` |
| 启动开发环境 | `cp .env.example .env && docker-compose up -d` |
