# 部署指南

## 一、两种部署模式

项目提供两套 Docker Compose 配置，适用于不同场景：

| | 开发版 `docker-compose.yml` | 生产版 `docker-compose.prod.yml` |
|---|---|---|
| **适用人群** | 开发者（改代码调试） | 家庭用户（自部署使用） |
| **后端** | `uvicorn --reload` 热重载 + 文件轮询 | 无热重载，用镜像内代码 |
| **前端** | Vite 开发服务器（HMR 热更新） | Vite preview（生产构建产物） |
| **源码挂载** | 挂载宿主机源码到容器 | 不挂载，用镜像内打包代码 |
| **APP_DEBUG** | true（SQL回显/详细日志） | false |
| **空闲 CPU** | ~5-15%（持续轮询） | ≈0% |
| **适合场景** | 本地开发调试 | NAS/小主机 7×24 小时运行 |

> 💡 **怎么选？**
> - **改代码** → 用开发版：`docker compose up -d`
> - **只是用** → 用生产版：`docker compose -f docker-compose.prod.yml up -d`
> - 两种模式共享数据库和用户数据，可随时切换，数据不丢失

---

## 二、Docker Compose 部署

### 前置要求

- Docker 20.10+ 及 Docker Compose v2+
- 模型 API Key（OpenAI 兼容接口）
- 最低配置：2 核 CPU / 2GB 内存 / 10GB 磁盘

### 家庭用户部署（生产版，推荐自部署用户使用）

```bash
# 1. 克隆仓库
git clone https://github.com/wangzhengpengjay/AI-Health-Steward.git
cd AI-Health-Steward

# 2. 复制环境配置
cp .env.example .env

# 3. 编辑 .env，至少配置以下项：
#    MULTIMODAL_API_BASE / MULTIMODAL_API_KEY / MULTIMODAL_API_MODEL  （必选）
#    TEXT_API_BASE / TEXT_API_KEY / TEXT_API_MODEL                    （推荐）
#    POSTGRES_PASSWORD                                                 （务必修改）
#    EMBEDDING_MODEL                                                   （可选，用于 RAG 报告检索）

# 4. 同步配置到 backend/.env（Docker 挂载使用此文件）
cp .env backend/.env

# 5. 构建镜像（首次部署）
docker compose -f docker-compose.prod.yml build

# 6. 启动（无热重载，低 CPU）
docker compose -f docker-compose.prod.yml up -d

# 7. 初始化数据库（首次部署）
docker exec health-steward-backend alembic upgrade head

# 8. 访问
# WebUI:  http://localhost:5173
# API 文档: http://localhost:8000/docs
```

> 生产版后端不挂载源码，使用镜像内打包的代码；前端使用 `vite preview` 提供生产构建产物。空闲时 CPU 占用接近 0%，适合长期运行。

### 开发者部署（开发版，改代码即时生效）

```bash
# 1. 克隆仓库
git clone https://github.com/wangzhengpengjay/AI-Health-Steward.git
cd AI-Health-Steward

# 2. 复制环境配置并填写
cp .env.example .env
# 编辑 .env，至少配置 MULTIMODAL_API_KEY 和 TEXT_API_KEY

cp .env backend/.env

# 3. 一键启动（热重载）
docker compose up -d

# 4. 初始化数据库（首次部署）
docker exec health-steward-backend alembic upgrade head

# 5. 访问
# WebUI: http://localhost:5173
# API 文档: http://localhost:8000/docs
```

> 开发版挂载宿主机源码到容器，改后端 Python 代码自动重载，改前端 TSX 代码 HMR 即时更新。

### 两种模式切换

数据库（`pgdata` volume）和用户数据（`./userdata`）两种模式共享，可随时切换：

```bash
# 开发 → 生产
docker compose down
docker compose -f docker-compose.prod.yml up -d

# 生产 → 开发
docker compose -f docker-compose.prod.yml down
docker compose up -d
```

### 常用命令

```bash
# 查看日志
docker compose logs -f backend
docker compose logs -f frontend

# 重启服务
docker compose restart backend

# 重建后端（代码变更后，开发版）
docker compose up -d --force-recreate backend

# 停止所有服务
docker compose down

# 停止并清除数据（谨慎）
docker compose down -v
```

## 三、配置说明

### 模型配置

| 配置项 | 说明 | 必选 |
|--------|------|------|
| `MULTIMODAL_API_BASE` | 多模态模型 API 地址（OpenAI 兼容） | 是 |
| `MULTIMODAL_API_KEY` | 多模态模型 API Key | 是 |
| `MULTIMODAL_API_MODEL` | 多模态模型名称（需支持视觉） | 是 |
| `TEXT_API_BASE` | 文字模型 API 地址 | 推荐 |
| `TEXT_API_KEY` | 文字模型 API Key | 推荐 |
| `TEXT_API_MODEL` | 文字模型名称 | 推荐 |
| `LOCAL_LLM_BASE` | 本地 LLM 地址（如 Ollama） | 可选 |
| `LOCAL_LLM_MODEL` | 本地 LLM 模型名称 | 可选 |
| `TEXT_PROVIDER_PRIORITY` | 文字模型优先级：`text_api` 或 `local_llm` | 默认 text_api |
| `EMBEDDING_API_BASE` | Embedding API 地址（留空回退到 TEXT_API_BASE） | 可选 |
| `EMBEDDING_API_KEY` | Embedding API Key（留空回退到 TEXT_API_KEY） | 可选 |
| `EMBEDDING_MODEL` | Embedding 模型名称（用于 RAG 检索） | 可选 |

### 数据库配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `POSTGRES_HOST` | postgres | Docker 模式用容器名，本地开发用 localhost |
| `POSTGRES_PORT` | 5432 | |
| `POSTGRES_DB` | health_steward | |
| `POSTGRES_USER` | health | |
| `POSTGRES_PASSWORD` | changeme | **生产环境务必修改** |

### 应用配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `APP_HOST` | 0.0.0.0 | |
| `APP_PORT` | 8000 | |
| `APP_DEBUG` | true | 生产环境建议设为 false |
| `CORS_ORIGINS` | http://localhost:5173 | 多个用逗号分隔 |

## 四、飞书 Bot 配置

### 创建飞书应用

1. 前往[飞书开放平台](https://open.feishu.cn/)创建企业自建应用
2. 开启**机器人能力**
3. 获取 `App ID` 和 `App Secret`

### 配置权限

在应用管理页面添加以下权限：
- `im:message` — 获取与发送单聊、群组消息
- `im:message:readonly` — 获取单聊、群组消息（读取消息内容）
- `im:resource` — 获取消息中的资源文件（下载图片）

### 启用 WebSocket 模式

1. 在「事件与回调」页面选择「长连接模式」
2. 订阅事件：`im.message.receive_v1`（接收消息）

### 在系统中配置

1. 打开 WebUI → 设置 → 飞书渠道
2. 点击「添加渠道」
3. 填写渠道名称、App ID、App Secret
4. 选择绑定的家庭成员（该渠道接收的消息和图片将归到此成员）
5. 保存后自动建立 WebSocket 连接

支持配置多个飞书渠道，每个渠道绑定不同的家庭成员。

## 五、本地开发部署（不用 Docker）

```bash
# 1. 启动数据库
docker compose up -d postgres

# 2. 后端
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env .env  # 复制配置
# 修改 POSTGRES_HOST=localhost
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# 3. 前端
cd frontend
npm install
npm run dev

# 4. 访问 http://localhost:5173
```

## 六、数据备份与恢复

```bash
# 备份
docker exec health-steward-db pg_dump -U health health_steward > backup.sql

# 恢复
docker exec -i health-steward-db psql -U health health_steward < backup.sql
```

上传的原始报告文件存储在 `userdata` 目录中（按 成员/年/月 组织）。

## 七、用户数据存储配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `USERDATA_DIR` | /app/userdata | 容器内报告文件存储路径 |
| `USERDATA_HOST_DIR` | ./userdata | 宿主机目录（Docker bind mount） |

报告文件按 `成员/年/月` 目录结构组织存储，可在系统设置页查看和管理。
