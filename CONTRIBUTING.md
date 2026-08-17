# 贡献指南

感谢你对 AI Health Steward 的关注！欢迎通过以下方式参与贡献。

## 提交 Issue

- Bug 报告：请描述复现步骤、预期行为、实际行为，附上相关日志
- 功能建议：请说明使用场景和期望效果
- 提问：先搜索已有 Issue，避免重复

## 提交 PR

1. Fork 仓库并创建分支：`git checkout -b feat/your-feature`
2. 确保代码能通过编译：后端 `python -c "from app.main import app"`，前端 `npx tsc --noEmit`
3. 如涉及新功能，请更新对应文档（OVERVIEW.md / DEVELOPMENT.md）
4. 提交信息使用约定式格式：
   - `feat: 新功能描述`
   - `fix: 修复描述`
   - `docs: 文档更新`
   - `refactor: 重构描述`
5. 提交 PR 并描述改动内容

## 开发环境

```bash
# 后端
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend
npm install
npm run dev

# 数据库
docker-compose up -d postgres
cd backend && alembic upgrade head
```

## 代码规范

- 后端：Python 类型注解 + async/await，遵循现有 FastAPI 模式
- 前端：TypeScript 严格模式，组件复用现有 UI 模式
- 命名：后端 snake_case，前端 camelCase
- 不引入新依赖，除非确有必要

## 项目结构

详见 [README](README.md) 的项目结构章节和 [开发者文档](DEVELOPMENT.md)。

## License

提交的贡献将遵循 [MIT License](LICENSE)。
