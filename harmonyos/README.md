# AI 健康管家 — 鸿蒙端

> HarmonyOS 原生应用，基于 ArkTS + ArkUI 开发

## 项目结构

```
harmonyos/
├── build-profile.json5          # 构建配置
├── oh-package.json5            # 项目配置
├── entry/                       # 主模块
│   ├── oh-package.json5
│   ├── src/main/
│   │   ├── module.json5         # 模块配置（权限、Ability 注册）
│   │   ├── ets/
│   │   │   ├── pages/
│   │   │   │   └── ChatPage.ets          # 对话页面（主页面）
│   │   │   ├── components/                # UI 组件（待开发）
│   │   │   ├── services/
│   │   │   │   ├── DatabaseService.ets    # ArkData RDB 数据库服务
│   │   │   │   ├── LLMClient.ets          # 云端 LLM API 客户端
│   │   │   │   ├── ConsultationService.ets # 咨询服务（对话+工具调用）
│   │   │   │   ├── PatrolEngine.ets       # 主动巡检引擎
│   │   │   │   ├── ReminderService.ets     # 代理提醒服务
│   │   │   │   └── PatrolWorkScheduler.ets # 后台延迟任务
│   │   │   ├── models/
│   │   │   │   └── HealthModels.ets        # 数据模型定义
│   │   │   ├── utils/                      # 工具类（待开发）
│   │   │   └── constants/                 # 常量定义（待开发）
│   │   └── resources/                      # 资源文件
│   │       ├── base/
│   │       │   ├── element/               # 字符串、颜色
│   │       │   ├── media/                 # 图片
│   │       │   └── profile/               # 页面路由配置
│   │       └── en_US/ zh_CN/              # 国际化
```

## 技术栈

| 技术 | 用途 |
|------|------|
| **ArkTS** | 开发语言（TypeScript 超集） |
| **ArkUI** | 声明式 UI 框架 |
| **ArkData RDB** | 本地数据库（SQLite 内核） |
| **@kit.BackgroundTasksKit** | 代理提醒 + 延迟任务 |
| **@kit.NotificationKit** | 通知管理 |
| **@ohos.net.http** | HTTP 网络请求（调用云端 LLM） |

## 核心能力

### 已实现（MVP 框架）

1. **数据模型** — 13 个表，完整对齐后端 PostgreSQL schema
2. **数据库服务** — ArkData RDB CRUD 操作
3. **LLM 客户端** — OpenAI 兼容 API 调用（非流式 + 流式 + 工具调用）
4. **咨询服务** — 对话管理 + 5 个工具调用 + 风险评估
5. **巡检引擎** — 画像快照 → 规则扫描 → AI 推理 → 频率控制
6. **代理提醒** — 定时推送 + App 被杀也能弹通知
7. **后台任务** — WorkScheduler 定时巡检
8. **对话页面** — 消息列表 + 流式输出 + 主动消息标记

### 待开发

- [ ] DevEco Studio 项目导入 + 编译验证
- [ ] EntryAbility 启动入口
- [ ] 成员管理页面
- [ ] 指标录入页面
- [ ] 画像看板页面
- [ ] 量表评估页面
- [ ] 结果回收服务（ArkTS 版）
- [ ] 延迟理解
- [ ] AppGallery Connect 申请代理提醒权限
- [ ] 真机调试

## 开发环境搭建

### 1. 安装 DevEco Studio

```bash
# 下载地址：https://developer.huawei.com/consumer/cn/deveco-studio/
# 选择 macOS (ARM) 版本
```

### 2. 导入项目

1. 打开 DevEco Studio
2. File → Open → 选择 `harmonyos/` 目录
3. 等待 SDK 同步完成

### 3. 配置签名

1. File → Project Structure → Signing Configs
2. 勾选 "Automatically generate signature"
3. 或手动配置 P12 文件 + Profile

### 4. 运行

1. 连接鸿蒙真机或启动模拟器
2. 点击 Run 按钮

## 权限申请

### 代理提醒权限（PUBLISH_AGENT_REMINDER）

⚠️ **需要在 AppGallery Connect 申请开放能力**，审核约 8 个工作日。

申请步骤：
1. 登录 [AppGallery Connect](https://developer.huawei.com/consumer/cn/agconnect/)
2. 我的项目 → 选择项目 → 开放能力
3. 申请"代理提醒"开放能力
4. 应用类型选择"运动健康"
5. 提交审核

### 通知权限

运行时动态申请：
```typescript
await notificationManager.requestEnableNotification();
```

## 与后端的关系

鸿蒙端是**完全独立的本地实现**，不依赖 Python 后端：

| 能力 | Web 后端 (Python) | 鸿蒙端 (ArkTS) |
|------|-------------------|----------------|
| 数据库 | PostgreSQL | ArkData RDB (SQLite) |
| 业务逻辑 | FastAPI + SQLAlchemy | ArkTS 原生实现 |
| LLM 调用 | httpx → DeepSeek API | @ohos.net.http → DeepSeek API |
| 巡检引擎 | patrol_engine.py | PatrolEngine.ets |
| 推送 | WebSocket / 轮询 | 代理提醒 + WorkScheduler |
| 数据同步 | — | Phase 3 规划中 |
