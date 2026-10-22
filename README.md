# 🏥 AI Health Steward | 本地 AI 健康管家

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)
[![Docker](https://img.shields.io/badge/deploy-Docker%20Compose-2496ed.svg?style=for-the-badge)](DEPLOYMENT.md)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB.svg?style=for-the-badge)](backend)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg?style=for-the-badge)](frontend)

[English](README_EN.md) · [在线介绍](https://wangzhengpengjay.github.io/AI-Health-Steward/)

> **市面上的健康 App 都是黑盒。你的化验结果、诊断、用药记录上传到别人的云上，被打包成产品卖。AI Health Steward 反过来——数据存在你自己的服务器上，AI 由你选择，手机也能用。**

---

## ✨ 核心能力

| 你想做的 | 传统 App | AI Health Steward |
|---|---|---|
| 体检报告解读 | 手动录入指标 | 拍照上传，AI 自动结构化提取 |
| AI 健康咨询 | 通用 chatbot | 基于你的实际画像数据回答 |
| 指标趋势追踪 | 手动记录 + 有限图表 | 血压/血糖/血脂/心率/体重趋势 + 危急值预警 |
| 体检推荐 | 通用套餐 | 基于画像的 1+X+Y 个性化方案 |
| 风险自测 | 下载各种 App | 9 大量表一站搞定（PHQ-9/GAD-7/糖尿病/心血管...） |
| 手机访问 | 必须用厂商云 | 自建服务器 + 配对码绑定，数据不经第三方 |
| 数据归属 | 数据在厂商手里 | 数据在你自己的硬盘上 |

---

## 🚀 快速开始

```bash
git clone https://github.com/zhengpengwangjay/AI-Health-Steward.git
cd AI-Health-Steward
cp .env.example .env          # 填入你的 API Key
cp .env backend/.env
mkdir -p userdata
docker compose -f docker-compose.prod.yml up -d

# 打开 http://localhost:5173 开始使用
```

**前置要求**：Docker 20.10+ · 模型 API Key（OpenAI 兼容，如 DeepSeek/GPT-4o）· 2 核 2GB 即可

### 📱 手机端连接

部署后，在设置页面一键生成配对码，手机输入地址 + 配对码即可绑定。支持 Cloudflare Tunnel / Caddy / Tailscale 三种公网方案，设置页面有完整引导。

---

## 🧠 为什么做这个

家里一堆体检报告，每次看完就忘。想用 AI 帮忙解读，但不想把家人的化验单传到陌生服务器。

**所以做了一个能跑在自己电脑上的健康管家**：

- 🔒 **数据从不上云** — 健康记录存在你自己的硬件上，不是某个 SaaS 的数据库
- 🏠 **一个实例服务整个家庭** — 多成员数据隔离，一人一套画像
- 🤖 **AI 由你选择** — 接 GPT-4o / DeepSeek / Ollama，云端或本地都行
- 📱 **手机也能用** — Capacitor 打包 iOS/Android，配对码绑定，公网安全访问
- 💰 **零成本** — MIT 开源，不需要订阅，不需要付费解锁功能

---

## 🏗️ 技术栈

| 层 | 技术 | 为什么选它 |
|---|---|---|
| 后端 | Python 3.12 + FastAPI | 异步性能好，自动生成 API 文档 |
| 前端 | React 18 + Vite + TypeScript + TailwindCSS | 现代前端，热重载开发体验好 |
| 数据库 | PostgreSQL 16 + pgvector | 支持 RAG 向量检索，健康报告语义搜索 |
| 移动端 | Capacitor | 复用 95% Web 代码，一套代码出 iOS/Android |
| AI | OpenAI 兼容 API + Ollama | 云端用 DeepSeek/GPT-4o，离线用 Ollama |

---

## 📦 项目结构

```
AI-Health-Steward/
├── backend/                 # Python FastAPI 后端
│   ├── app/
│   │   ├── api/routes/      # 14 个 API 模块（咨询/报告/画像/配对/飞书...）
│   │   ├── core/            # 安全 · 鉴权 · 限流 · 参考范围
│   │   ├── models/          # 数据模型（含配对设备）
│   │   ├── services/        # 业务逻辑（AI咨询/抽取/巡检引擎/记忆压缩）
│   │   └── providers/       # 模型抽象层（多模态/文字/本地/嵌入）
│   └── alembic/             # 数据库迁移
├── frontend/                # React 前端（WebUI）
│   └── src/
│       ├── components/      # MobileNav · MobileHeader · ChatBubble...
│       ├── pages/           # 12 个页面
│       ├── stores/          # Zustand 状态管理
│       └── lib/             # API 封装 + 配对客户端
├── docker-compose.yml       # 开发模式（热重载）
├── docker-compose.prod.yml   # 生产模式（7×24 稳定运行）
└── .env.example             # 配置模板（Key 都是占位符）
```

---

## 🔐 隐私边界

| 数据 | 去哪里 | 你能控制吗 |
|---|---|---|
| 健康记录、报告、画像 | **你的服务器** | ✅ 随时导出/删除 |
| 对话内容、报告图片 | **你选择的模型 API** | ✅ 用 Ollama 可完全离线 |
| 配对 Token | **手机 Keychain/Keystore** | ✅ 可随时吊销设备 |
| 健康数据 | **不上传任何第三方** | ✅ 数据在你的硬盘上 |

---

## 📋 完整功能清单

<details>
<summary>点击展开全部功能</summary>

- **多模态报告导入** — 拍照上传体检报告/化验单，AI 自动结构化抽取关键指标
- **人维度健康画像** — 基础信息/生理指标/诊断/用药/过敏/生活方式/家族史全字段
- **AI 健康咨询** — 意图路由 + 工具调用，回答基于你的实际画像数据
- **指标趋势可视化** — 血压/血糖/血脂/心率/体重趋势图，异常标识与危急值预警
- **个性化体检推荐** — 1+X+Y 三层逻辑生成定制化体检方案
- **风险自测量表** — 9 大量表（PHQ-9 抑郁/GAD-7 焦虑/糖尿病/心血管/失眠等）
- **主动健康 Agent** — 定时巡检、规则+AI 双层判断、自动推送健康提醒
- **复测/用药待办** — 基于危急值、异常指标、用药自动生成待办任务
- **健康小结** — 周/月/年周期自动生成指标趋势与建议汇总
- **报告语义检索 (RAG)** — 入档报告自动向量化，AI 咨询可语义检索历史报告
- **飞书集成** — 多 Bot 多成员，WebSocket 长连接，随手丢报告
- **手机端** — Capacitor WebView，配对码绑定，公网安全访问
- **长期会话记忆** — 每次咨询后增量压缩为成员长期记忆
- **年龄分档参考范围** — 血压/血糖等按成人/儿童自动匹配正常范围
- **就诊准备** — 主诉驱动科室推荐，AI 生成就诊清单，PDF 导出

</details>

---

## 🤝 贡献

欢迎提交 Issue 和 PR。请先阅读 [贡献指南](CONTRIBUTING.md)。

## 📖 文档

- [部署指南](DEPLOYMENT.md) · [开发者文档](DEVELOPMENT.md) · [隐私声明](PRIVACY.md)

## License

[MIT](LICENSE)
