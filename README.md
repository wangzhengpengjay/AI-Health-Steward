# AI Health Steward | 本地 AI 健康管家
[English](README_EN.md)


> 开源、可私有化部署的家庭 AI 健康管家。通过多模态大模型将健康数据结构化为人维度画像，提供可视化看板与 AI 咨询能力，支持飞书等渠道的资料收集与轻问答。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 特性

- **本地私有部署** — 健康数据存储在本地，自主可控
- **多模态报告导入** — 拍照上传体检报告/化验单/处方，AI 自动结构化抽取关键指标
- **人维度健康画像** — A-H 全字段族（基础信息/生理指标/诊断/用药/过敏/生活方式/家族史/数据溯源），作为单一事实来源
- **AI 健康咨询** — 意图路由 + 工具调用，回答基于你的实际画像数据，非通用 chatbot
- **指标趋势可视化** — 血压/血糖/血脂/心率/体重 BMI 趋势图，异常标识
- **个性化体检推荐** — 基于健康画像，按 1+X+Y 三层逻辑（基础核心集/现状深度专项/风险预警专项）生成定制化体检方案，支持预算档位选择与安全禁忌排查
- **多渠道接入** — WebUI 为主界面，飞书 Bot 做资料收集与轻问答
- **模型可插拔** — 多模态 API（必选）/ 文字 API（可选）/ 本地 LLM（可选），按需配置
- **家庭多成员** — 单实例服务一个家庭，成员数据隔离
- **报告管理** — 报告全生命周期管理（上传→AI抽取→确认入档→归档），支持从报告管理页、指标管理页、AI 咨询页三个入口上传，入档数据自动归入健康画像
- **检验检查追踪** — 检验指标按报告分组独立曲线追踪，检查异常发现按分类时间轴展示
- **AI 图片解读** — 咨询中发送报告图片，AI 先多模态抽取结构化数据，再基于数据做专业解读，同时支持一键入档

## 快速开始

### 前置要求

- Docker 20.10+ 和 docker-compose v2+
- 模型 API Key（OpenAI 兼容接口，支持 GPT-4o / DeepSeek 等）
- 最低配置：2 核 CPU / 2GB 内存 / 10GB 磁盘

### 部署

```bash
# 1. 克隆仓库
git clone https://github.com/wangzhengpengjay/AI-Health-Steward.git
cd ai-health-steward

# 2. 复制环境配置并填写
cp .env.example .env
# 编辑 .env，至少配置 MULTIMODAL_API_KEY 和 TEXT_API_KEY

# 3. 一键启动
docker-compose up -d

# 4. 访问
# WebUI: http://localhost:5173
# API 文档: http://localhost:8000/docs
```

## 技术栈

| 层 | 技术 |
|---|------|
| 后端 | Python 3.12 + FastAPI |
| 前端 | React 18 + Vite + TypeScript + TailwindCSS |
| 数据库 | PostgreSQL 16 + pgvector |
| ORM | SQLAlchemy 2.0 + Alembic |
| AI | OpenAI 兼容 API（多模态/文字）+ Ollama（本地 LLM） |
| 部署 | Docker Compose |

## 项目结构

```
ai-health-steward/
├── backend/                 # Python FastAPI 后端
│   ├── app/
│   │   ├── api/             # API 路由
│   │   ├── core/            # 配置、数据库
│   │   ├── models/          # SQLAlchemy 数据模型
│   │   ├── schemas/         # Pydantic 数据校验
│   │   ├── services/        # 业务逻辑
│   │   ├── prompts/         # AI 指令模板
│   │   └── providers/       # 模型 provider 抽象
│   ├── alembic/             # 数据库迁移
│   └── tests/               # 测试
├── frontend/                # React 前端
│   └── src/
│       ├── components/      # UI 组件
│       ├── pages/           # 页面
│       ├── hooks/           # React Hooks
│       ├── lib/             # API 请求等工具
│       ├── stores/          # Zustand 状态管理
│       └── types/           # TypeScript 类型
├── openspec/                # 需求文档与架构设计
│   └── changes/ai-health-steward/
│       ├── proposal.md      # 需求概述
│       ├── design.md        # 架构决策与技术选型
│       ├── tasks.md         # 版本规划与任务
│       ├── specs/           # 六个 capability 的详细规格
│       └── UI-DESIGN-SYSTEM.md  # UI 设计系统规范
├── docker-compose.yml
├── .env.example
└── README.md
```

## 版本路线

| 版本 | 目标 | 状态 |
|------|------|------|
| V0.1 | 项目骨架与数据地基 — 能存数据、能看画像 | ✅ 已完成 |
| V0.2 | AI 咨询能力 — 意图路由、工具调用、对话界面 | ✅ 已完成 |
| V0.3 | 报告导入与可视化 — 多模态抽取、趋势图、画像看板、报告管理、体检推荐 | 🔧 开发中 |
| V0.4 | 飞书渠道 — 资料收集、轻问答 | 规划中 |
| V1.0 | 开源发布 — 文档完善、一键部署 | 规划中 |

## 项目截图

![健康画像看板](docs/screenshots/dashboard-overview.png)
![AI咨询报告解读](docs/screenshots/chat-report-extraction.png)
![指标管理与录入](docs/screenshots/metric-input.png)

## 隐私声明

- **数据存储**：所有健康数据存储在本地服务器，不上传到任何云端
- **模型调用**：对话内容和报告图片在调用云端模型 API 时会发送给 provider。如需完全离线，可配置本地 LLM（如 Ollama）
- **数据导出**：用户可随时导出全部健康数据（JSON 格式）
- **数据删除**：支持单条记录删除和整成员删除（软删除 30 天后硬删除）

详见 [隐私声明](PRIVACY.md)。

## 贡献

欢迎提交 Issue 和 PR。请先阅读 [贡献指南](CONTRIBUTING.md) 和 [需求文档](openspec/changes/ai-health-steward/proposal.md) 了解项目方向。

## License

[MIT](LICENSE)
