# 开发者文档

## 项目架构

```
用户 → WebUI (React) → API (FastAPI) → PostgreSQL + pgvector
                         ↓
                    Model Router → 多模态 API / 文字 API / 本地 LLM
                         ↓
                    飞书 Bot (WebSocket)
```

### 后端结构

```
backend/app/
├── api/
│   ├── routes/          # 路由模块
│   │   ├── members.py       # 家庭成员 CRUD
│   │   ├── metrics.py       # 指标查询与手动录入
│   │   ├── chat.py          # AI 咨询（SSE 流式 + 历史分页）
│   │   ├── reports.py       # 报告上传/抽取/确认/状态机
│   │   ├── checkup.py       # 体检推荐
│   │   ├── profile.py       # 健康画像 CRUD
│   │   ├── scales.py        # 风险自测量表（V1.1）
│   │   ├── tasks.py         # 待办任务管理（V1.1）
│   │   ├── summaries.py     # 健康小结（V1.1）
│   │   ├── settings.py      # 系统设置与配置管理
│   │   ├── providers.py     # 模型 Provider 状态查询
│   │   └── feishu.py        # 飞书渠道管理
│   └── v1/router.py     # 路由聚合（挂载全局鉴权）
├── core/
│   ├── config.py          # Pydantic Settings（从 .env 加载，含 USERDATA_DIR）
│   ├── database.py        # 异步 SQLAlchemy 引擎
│   ├── security.py        # Bearer Token 鉴权 + 滑动窗口限流
│   ├── reference_ranges.py # 成人/儿童参考范围 + 临床危急值
│   └── utils.py           # 工具函数（compute_age / metric_label / parse_model_json）
├── models/
│   ├── family.py          # 家庭成员模型
│   ├── health.py          # 健康数据模型（A-H 字段族 + 报告 + 体检 + 向量）
│   ├── assessments.py     # 量表测评结果模型（V1.1）
│   ├── tasks.py           # 健康待办任务模型（V1.1）
│   ├── summaries.py       # 健康小结模型（V1.1）
│   └── feishu.py          # 飞书渠道配置模型
├── providers/
│   ├── base.py            # ModelProvider 抽象接口
│   ├── multimodal.py      # 多模态 API provider
│   ├── text.py            # 文字 API provider
│   ├── local_llm.py       # 本地 LLM provider
│   ├── embedding.py       # Embedding provider（RAG）
│   └── router.py          # 模型路由器
├── services/
│   ├── consultation.py    # AI 咨询编排（多模态抽取→文字解读→工具调用）
│   ├── extractor.py       # 指标抽取（多批次 Map-Reduce + 合并）
│   ├── extraction_rules.py # 抽取后处理规则（去重/标准化）
│   ├── image_utils.py     # 图片预处理（方向校正/压缩）
│   ├── file_storage.py    # 用户报告文件存储（按成员/年/月）
│   ├── member_memory.py   # 长期会话记忆（增量压缩）
│   ├── checkup_recommend.py # 1+X+Y 体检推荐（LLM 版）
│   ├── checkup_rules.py   # 体检推荐规则引擎（确定性版）
│   ├── task_service.py    # 待办任务自动生成 + 管理（V1.1）
│   ├── summary_service.py # 健康小结生成（规则+LLM）（V1.1）
│   ├── summary_scheduler.py # 小结定期自动触发调度器（V1.1）
│   ├── rag.py             # 报告向量化与语义检索
│   ├── feishu.py          # 飞书多渠道 Bot 管理
│   └── tools/             # AI 工具（function calling）
│       ├── base.py          # HealthTool 抽象
│       ├── registry.py      # 工具注册中心
│       ├── query_metrics.py # 指标查询工具
│       ├── query_profile.py # 画像查询工具
│       ├── query_abnormal.py # 异常项查询工具
│       ├── query_reports.py  # 报告语义检索工具（RAG）
│       ├── extract_and_save.py # 对话抽取回填工具
│       └── assess_scale.py  # 量表测评工具（V1.1）
└── prompts/
    ├── __init__.py        # 提示词常量（EXTRACT_PROMPT 等）
    └── checkup_system_v1.md  # 体检推荐系统指令
```

### 前端结构

```
frontend/src/
├── pages/
│   ├── Home.tsx              # 家庭健康速览（默认首页）
│   ├── Dashboard.tsx        # 健康画像看板（含危急值预警）
│   ├── Chat.tsx             # AI 咨询（SSE 流式 + 图片解读）
│   ├── Reports.tsx          # 报告管理
│   ├── MetricInput.tsx      # 指标管理与可视化
│   ├── CheckupRecommend.tsx # 体检推荐
│   ├── Members.tsx          # 家庭成员管理
│   ├── Assess.tsx           # 风险自测量表（V1.1）
│   ├── AssessResult.tsx     # 量表结果页（V1.1）
│   ├── Summaries.tsx        # 健康小结查看（V1.1）
│   └── Settings.tsx         # 系统设置
├── components/
│   ├── Layout.tsx           # 全局布局与导航
│   ├── Sidebar.tsx          # 侧边栏
│   ├── MemberSwitcher.tsx   # 成员切换器
│   ├── ChatBubble.tsx       # 对话气泡（Markdown 渲染）
│   ├── MetricViews.tsx      # 指标趋势图组件
│   ├── ReportConfirmModal.tsx # 报告确认面板
│   └── CheckupSupplementModal.tsx # 体检信息补充问卷
├── stores/
│   ├── memberStore.ts       # Zustand 全局成员状态
│   └── chatStore.ts         # Zustand 对话状态
├── lib/
│   └── api.ts               # API 请求封装
└── types/
    └── index.ts             # TypeScript 类型定义
```

## 扩展指南

### 添加新的模型 Provider

1. 在 `backend/app/providers/` 下新建文件，继承 `ModelProvider`
2. 实现 `chat()` 和 `health_check()` 方法
3. 在 `router.py` 中注册并配置路由逻辑

```python
from app.providers.base import ModelProvider, ProviderCapability, Message, ModelResponse

class MyProvider(ModelProvider):
    def __init__(self, base_url, api_key, model):
        super().__init__("my_provider", base_url, api_key, model,
                         ProviderCapability.TEXT | ProviderCapability.TOOL_CALLING)

    async def chat(self, messages, *, tools=None, temperature=0.7, max_tokens=4096, stream=False):
        # 实现 API 调用逻辑
        ...

    async def health_check(self):
        ...
```

### 添加新的 AI 工具

1. 在 `backend/app/services/tools/` 下新建文件，继承 `HealthTool`
2. 定义 `name`、`description`、`parameters`
3. 实现 `execute()` 方法
4. 在 `registry.py` 中注册

```python
from app.services.tools.base import HealthTool

class MyTool(HealthTool):
    name = "my_tool"
    description = "工具描述，模型会根据此描述决定是否调用"
    parameters = {
        "type": "object",
        "properties": {"param": {"type": "string", "description": "参数说明"}},
        "required": ["param"],
    }

    async def execute(self, db, member_id, **kwargs):
        return {"result": "..."}
```

### 添加新的消息渠道

1. 在 `backend/app/models/` 下新建渠道配置模型（参考 `feishu.py`）
2. 在 `backend/app/services/` 下实现渠道 Bot 服务
3. 在 `backend/app/api/routes/` 下添加管理端点
4. 在 `main.py` 的 lifespan 中启动渠道连接
5. 在前端设置页添加渠道配置 UI

### 数据库迁移

```bash
# 生成新迁移
cd backend && alembic revision --autogenerate -m "描述"

# 执行迁移
alembic upgrade head

# 回滚
alembic downgrade -1
```

## 开发约定

- 后端：Python 类型注解 + async/await，snake_case
- 前端：TypeScript 严格模式，camelCase，组件复用现有 UI 模式
- 不引入新依赖，除非确有必要
- 提交信息：`feat:` / `fix:` / `docs:` / `refactor:` / `style:`
