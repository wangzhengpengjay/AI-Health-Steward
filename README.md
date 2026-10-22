# AI Health Steward | 本地 AI 健康管家

[English](README_EN.md)

> 自托管、隐私优先的家庭 AI 健康管家。多模态大模型将体检报告、化验单结构化为家庭成员健康画像，提供 AI 咨询、指标趋势、体检推荐、风险自测等能力。数据全部存在你自己的服务器上。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![在线介绍](https://img.shields.io/badge/%F0%9F%93%96%20%E5%9C%A8%E7%BA%BF%E4%BB%8B%E7%BB%8D-online-brightgreen)](https://wangzhengpengjay.github.io/AI-Health-Steward/)

---

## 为什么做这个项目

市面上的健康 App 都是黑盒——你的化验结果、诊断、用药记录上传到别人的云上，被打包成产品卖。**AI Health Steward 反过来。**

- **数据从不离开你的服务器**——健康记录、报告、画像全部存在你自己的硬件上
- **一个实例服务整个家庭**——多成员数据隔离
- **自带 AI**——接入任何 OpenAI 兼容模型（GPT-4o、DeepSeek 等），或用本地 LLM（Ollama）完全离线
- **手机也能用**——Capacitor 打包 iOS/Android App，配对码绑定，公网安全访问

> 健康记录是你最敏感的数据。它不应该是产品，应该放在你自己的架子上。

---

## 核心功能

- **多模态报告导入** — 拍照上传体检报告/化验单，AI 自动结构化抽取关键指标
- **人维度健康画像** — 基础信息/生理指标/诊断/用药/过敏/生活方式/家族史全字段
- **AI 健康咨询** — 基于你的实际画像数据回答，不是通用 chatbot
- **指标趋势可视化** — 血压/血糖/血脂/心率/体重趋势图，异常标识与危急值预警
- **个性化体检推荐** — 1+X+Y 三层逻辑生成定制化体检方案
- **风险自测量表** — 9 大量表（PHQ-9 抑郁/GAD-7 焦虑/糖尿病/心血管/失眠等）
- **主动健康 Agent** — 定时巡检、规则+AI 双层判断、自动推送健康提醒
- **复测/用药待办** — 基于危急值、异常指标、用药自动生成待办任务
- **健康小结** — 周/月/年周期自动生成指标趋势与建议汇总
- **飞书集成** — 多 Bot 多成员，WebSocket 长连接，随手丢报告
- **手机端** — Capacitor WebView，配对码绑定，公网安全访问

---

## 快速开始

### 前置要求

- Docker 20.10+ 和 docker-compose v2+
- 模型 API Key（OpenAI 兼容接口，支持 GPT-4o / DeepSeek 等）
- 最低配置：2 核 CPU / 2GB 内存 / 10GB 磁盘

### 部署

```bash
# 1. 克隆仓库
git clone https://github.com/zhengpengwangjay/AI-Health-Steward.git
cd AI-Health-Steward

# 2. 复制环境配置并填写
cp .env.example .env
# 编辑 .env，至少配置 MULTIMODAL_API_KEY 和 TEXT_API_KEY

# 3. 同步配置到 backend/.env
cp .env backend/.env

# 4. 创建用户数据目录
mkdir -p userdata

# 5. 构建并启动（生产模式）
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d

# 6. 访问
# WebUI: http://localhost:5173
# API 文档: http://localhost:18000/docs
```

> 开发模式（热重载）用 `docker compose up -d` 即可。两种模式共享数据库和用户数据。

### 手机端连接

部署完成后，在 WebUI 设置页面配置公网访问：

1. 打开 **设置 → 移动设备配对**
2. 选择固定域名方案（Cloudflare Tunnel / Caddy / Tailscale）
3. 按引导配置固定地址
4. 生成配对码，在手机 App 中输入地址和配对码

详细步骤见设置页面的配置引导面板。

---

## 技术栈

| 层 | 技术 |
|---|------|
| 后端 | Python 3.12 + FastAPI |
| 前端 | React 18 + Vite + TypeScript + TailwindCSS |
| 数据库 | PostgreSQL 16 + pgvector |
| 移动端 | Capacitor（iOS / Android） |
| AI | OpenAI 兼容 API（多模态/文字）+ Ollama（本地 LLM） |
| 部署 | Docker Compose |

---

## 项目结构

```
AI-Health-Steward/
├── backend/                 # Python FastAPI 后端
│   ├── app/
│   │   ├── api/routes/      # API 路由（成员/指标/咨询/报告/体检/画像/设置/飞书/量表/待办/小结/配对）
│   │   ├── core/            # 配置、数据库、鉴权限流、安全
│   │   ├── models/          # 数据模型（家庭成员/健康画像/报告/飞书/量表/待办/小结/配对设备）
│   │   ├── services/        # 业务逻辑（AI咨询/抽取/体检推荐/飞书/记忆/待办/小结/巡检引擎）
│   │   │   └── tools/       # AI 工具（function calling）
│   │   ├── prompts/         # AI 指令模板
│   │   └── providers/       # 模型 provider 抽象（多模态/文字/本地/嵌入）
│   ├── alembic/             # 数据库迁移
│   └── tests/               # 单元测试
├── frontend/                # React 前端（WebUI）
│   └── src/
│       ├── components/      # UI 组件
│       ├── pages/           # 页面
│       ├── stores/          # Zustand 状态管理
│       └── lib/             # API 请求封装
├── docker-compose.yml       # 开发部署（热重载）
├── docker-compose.prod.yml  # 生产部署（无热重载）
├── .env.example             # 环境变量模板
└── README.md
```

---

## 隐私声明

- **数据存储**：所有健康数据存储在本地服务器，不上传到任何云端
- **模型调用**：对话内容和报告图片在调用云端模型 API 时会发送给你配置的 provider。如需完全离线，可配置本地 LLM（如 Ollama）
- **数据导出**：用户可随时导出全部健康数据（JSON 格式）
- **数据删除**：支持单条记录删除和整成员删除（软删除 30 天后硬删除）
- **手机配对**：配对 Token 存储在 iOS Keychain / Android Keystore，不上传到任何第三方

---

## 贡献

欢迎提交 Issue 和 PR。请先阅读 [贡献指南](CONTRIBUTING.md)。

## 文档

- [部署指南](DEPLOYMENT.md) — Docker 部署、配置说明、飞书 Bot 配置
- [开发者文档](DEVELOPMENT.md) — 项目架构、扩展指南
- [隐私声明](PRIVACY.md) — 数据存储与模型调用边界

## License

[MIT](LICENSE)
