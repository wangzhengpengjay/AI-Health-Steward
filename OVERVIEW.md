# 本地 AI 健康管家 - 项目总览

> 本文档是项目的导航入口，说明文件架构、每份文件的作用，以及接下来的行动项。
> 最后更新：2026-07-22

---

## 一、项目定位

| 维度 | 说明 |
|------|------|
| 产品形态 | 本地私有化部署的家庭 AI 健康管家，开源项目 |
| 第一用户 | 本人 + 家庭，单实例服务一个家庭 |
| 模型策略 | API 为主（多模态必选、文字可选），兼容本地 LLM |
| 主界面 | WebUI 承载完整功能 |
| 渠道扩展 | 飞书（资料收集 + 轻问答），后续邮件等 |
| 与晓医关系 | 完全独立，无代码/数据复用，功能上部分重叠，后续按需参照 |

---

## 二、文件架构

```
ai-native/
├── OVERVIEW.md                          ← 你正在看的这份文档
└── openspec/
    ├── config.yaml                      ← OpenSpec 配置（schema: spec-driven）
    └── changes/
        └── ai-health-steward/           ← 本次需求变更的完整规划
            ├── .openspec.yaml           ← change 元数据（schema/创建时间/goal）
            ├── README.md                ← change 简述（自动生成）
            ├── proposal.md              ← 【需求概述】为什么做、改什么、capability 划分
            ├── design.md                ← 【架构决策】7 个技术决策 + 风险 + 开放问题
            ├── tasks.md                 ← 【版本规划】V0.1-V1.0 共 5 版 35 个任务
            └── specs/                   ← 【能力规格】6 个 capability 的详细需求
                ├── health-profile/      ← 健康画像与数据管理
                │   └── spec.md
                ├── report-ingestion/    ← 报告导入与多模态抽取
                │   └── spec.md
                ├── ai-consultation/     ← AI 健康咨询
                │   └── spec.md
                ├── visualization/       ← 健康数据可视化
                │   └── spec.md
                ├── channels/            ← 多渠道接入
                │   └── spec.md
                └── model-provider/      ← 模型层抽象
                    └── spec.md
```

---

## 三、文件说明

### 3.1 规划层（OpenSpec artifacts）

| 文件 | 作用 | 什么时候看 |
|------|------|-----------|
| `proposal.md` | 需求的「为什么」和「做什么」。定义了 6 个 capability 的边界，是整个变更的契约 | 想回顾"我们到底要做什么"时 |
| `design.md` | 需求的「怎么做」。7 个架构决策（D1-D7）讲了为什么这样选、备选方案是什么。还列了风险和 5 个待定开放问题 | 做技术选型或架构评审时 |
| `tasks.md` | 实施的「什么时候做」。V0.1 到 V1.0 五个版本，35 个可勾选任务，按依赖排序 | 进入开发、跟踪进度时 |
| `specs/*/spec.md` | 每个 capability 的详细需求规格，用 SHALL/MUST 规范语句 + WHEN/THEN 场景描述。每个场景就是一个可测试用例 | 开发某个功能前看对应 spec |

### 3.2 六个 capability 说明

| Capability | spec 路径 | 覆盖什么 |
|------------|----------|----------|
| `health-profile` | `specs/health-profile/spec.md` | 家庭成员 CRUD、A-H 字段族、三种数据入档路径、数据溯源、画像作为单一事实来源 |
| `report-ingestion` | `specs/report-ingestion/spec.md` | 图片/PDF 上传、模型按输入类型路由、多模态结构化抽取、姓名识别与归属匹配 |
| `ai-consultation` | `specs/ai-consultation/spec.md` | 意图路由器、六类健康意图、工具调用框架、角色知识边界、聊天抽取回填闭环 |
| `visualization` | `specs/visualization/spec.md` | 第一梯队指标趋势图、异常标识、画像看板 |
| `channels` | `specs/channels/spec.md` | WebUI 主界面、飞书资料收集、飞书轻问答、渠道适配层抽象 |
| `model-provider` | `specs/model-provider/spec.md` | 三类 provider、多模态必选依赖、本地 LLM 仅兜文字、路由逻辑 |

### 3.3 配置文件

| 文件 | 作用 |
|------|------|
| `openspec/config.yaml` | OpenSpec 项目配置，当前 schema 为 `spec-driven` |
| `.openspec.yaml` | change 元数据，记录 schema、创建时间、goal |

---

## 四、版本规划速览

```
V0.1 核心骨架        V0.2 AI 咨询        V0.3 报告+可视化      V0.4 飞书          V1.0 开源发布
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   ┌──────────────┐
│ 项目脚手架    │    │ 意图路由器    │    │ 图片/PDF上传 │    │ 渠道适配抽象  │   │ 部署文档     │
│ 模型层抽象    │───▶│ 工具调用框架  │───▶│ 多模态抽取   │───▶│ 飞书Bot接入  │──▶│ 隐私声明     │
│ 画像数据模型  │    │ 六类意图实现  │    │ 趋势图+异常  │    │ 资料收集     │   │ 示例数据     │
│ 家庭成员管理  │    │ 聊天抽取回填  │    │ 画像看板     │    │ 轻问答       │   │ 开发者文档   │
│ 手动录入入档  │    │ 角色知识边界  │    │ 向量化知识库 │    │              │   │ README       │
│ 基础WebUI    │    │ 对话界面     │    │              │    │              │   │              │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘   └──────────────┘
  能存能看             能聊               能看趋势           能随手丢            能fork能跑
```

每个版本的目标是一句话：V0.1 数据能存进去画像能看出来；V0.2 能和 AI 聊健康 AI 懂你的画像；V0.3 报告能进系统趋势能看出来；V0.4 飞书能丢报告能随口问；V1.0 开发者能 fork 能跑能改。

---

## 五、接下来你需要干什么

### 5.1 立即要做（进入开发前）

1. **审查 PRD**：通读 `proposal.md` 和 `design.md`，确认需求和理解无误。有要改的地方告诉我。
2. **确定参照点**：你前面提到"后面会说怎么参照晓医"。确定哪些功能/设计要参照晓医的做法，我会更新进 `design.md`。
3. **技术评审**：`design.md` 末尾列了 5 个开放问题，需要你拍板或组织评审：
   - 技术栈选型（Python/FastAPI + React？Node 全栈？）
   - 结构化存储选 SQLite 还是 Postgres
   - 向量库选型（Chroma / Qdrant / pgvector）
   - 飞书机器人审核流程
   - 多模态抽取 JSON schema 形态（预定义 vs 自由输出后校验）

### 5.2 开发阶段

4. **启动 V0.1**：技术栈定了之后，我按 `tasks.md` 的 1.1-1.10 开始实现。
5. **逐版本验收**：每个版本完成后，对照该版本的目标和 spec 场景验收。

### 5.3 发布阶段

6. **开源准备**：V1.0 阶段一起完善文档、隐私声明、示例数据。
7. **commit 到仓库**：PRD 定稿后，将 openspec 目录 commit 到项目仓库。

---

## 六、接下来我会干什么

### 6.1 等你确认后

- 根据你的审查意见修改 `proposal.md` / `design.md` / `specs/`
- 根据你提供的晓医参照点，更新 `design.md` 对应决策
- 如果开放问题你有倾向，我会把决策写进 `design.md`

### 6.2 进入开发后

- 按 `tasks.md` 顺序实现，每个任务完成后勾选
- 实现过程中如发现 spec 有遗漏或矛盾，会回来更新 spec
- 每个版本完成后做一次验收，对照 spec 场景检查

### 6.3 我不会主动做的事

- 不替你做技术选型决策（开放问题等你拍板）
- 不替你决定参照晓医哪些功能（等你给方向）
- 不在 PRD 未定稿前开始写实现代码

---

## 七、快速导航

| 我想... | 看哪里 |
|--------|--------|
| 回顾需求全貌 | `openspec/changes/ai-health-steward/proposal.md` |
| 理解架构决策 | `openspec/changes/ai-health-steward/design.md` |
| 看版本规划和任务 | `openspec/changes/ai-health-steward/tasks.md` |
| 看某个功能的详细需求 | `openspec/changes/ai-health-steward/specs/<capability>/spec.md` |
| 校验 OpenSpec 状态 | `cd ai-native && openspec validate ai-health-steward --json` |
| 查看 change 状态 | `cd ai-native && openspec status --change ai-health-steward --json` |
