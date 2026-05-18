# AI Memory Card Onboarding Guide

这份文档写给第一次打开仓库的开发者。它说明这个 GitHub 项目里哪些文件必须保留、代码应该从哪里读起、修改时要尊重哪些边界。

## 1. 这个仓库应该包含什么

公开仓库只保留能支撑应用开发、测试、发布和协作的内容：

```text
.github/workflows/ci.yml          GitHub Actions 自动验证
.gitignore                        过滤本地运行时数据和构建产物
LICENSE                           开源协议
README.md                         项目介绍、快速启动和宣传入口
apps/local-web/backend            FastAPI 后端
apps/local-web/frontend           React/Vite 前端
apps/local-web/desktop            Tauri 桌面壳和发布脚本
apps/local-web/plugins/rag-core   本地 AI 插件运行时
docs/onboarding-guide.md          新开发者入门
docs/development.md               工程边界、命名、验证和清理策略
docs/integration                  AI provider 集成说明
docs/release                      Windows 发布和冒烟测试说明
```

## 2. 一分钟理解项目

AI Memory Card 是一个本地优先的智能复习系统。它做三件事：

1. 从教材、讲义、笔记等资料中生成结构化知识单元和记忆卡。
2. 通过大模型分析学生主动解释，评估概念、机制、边界和误区。
3. 结合传统调度和可选 AI/RL 建议，给出复习间隔。

关键设计原则：**后端拥有最终状态，AI 插件只提供建议**。卡片、复习记录、学习事件和调度状态最终都由 FastAPI 后端写入 SQLite。

## 3. 工程地图

```text
apps/local-web/
  frontend/     React + TypeScript + Vite
  backend/      FastAPI + SQLModel + Alembic
  desktop/      Tauri + Rust + Node release scripts
  plugins/
    rag-core/   RAG、理解评估、AI/RL 调度建议
```

推荐阅读顺序：

1. `README.md`
2. `docs/development.md`
3. `apps/local-web/frontend/src/app/router.tsx`
4. `apps/local-web/backend/app/main.py`
5. `apps/local-web/backend/app/db/models.py`
6. `apps/local-web/plugins/rag-core/plugin.json`

## 4. 前端怎么读

前端目录：`apps/local-web/frontend`

| 目标 | 文件 |
| --- | --- |
| 应用入口 | `src/main.tsx` |
| 路由 | `src/app/router.tsx` |
| 左侧导航和布局 | `src/app/shell.tsx` |
| 复习页 | `src/pages/review-page.tsx` |
| 牌库页 | `src/pages/library-page.tsx` |
| 数据分析页 | `src/pages/data-page.tsx` |
| 复习历史页 | `src/pages/review-history-page.tsx` |
| 设置页 | `src/pages/settings-page.tsx` |
| API 请求 | `src/api` |
| UI 基础组件 | `src/components/ui` |
| 中英文文案 | `src/i18n/locales` |

约定：

- `pages` 负责路由级页面骨架。
- `features` 负责具体业务组件。
- `api` 负责 HTTP/Tauri 调用封装。
- `components/ui` 只放通用 UI 原语。

## 5. 后端怎么读

后端目录：`apps/local-web/backend`

| 目标 | 文件 |
| --- | --- |
| FastAPI 总入口 | `app/main.py` |
| HTTP 路由 | `app/api/routes` |
| 依赖注入 | `app/api/dependencies.py` |
| 数据库模型 | `app/db/models.py` |
| 数据库连接 | `app/db/session.py` |
| Alembic 迁移 | `alembic/versions` |
| 请求/响应 schema | `app/schemas` |
| 业务服务 | `app/services` |
| 可替换 provider | `app/providers` |
| 后端测试 | `tests` |

核心服务：

- `CardService`: 卡片管理。
- `RAGImportService`: 将插件生成的卡片和知识单元写入数据库。
- `EvaluationService`: 主动解释评估。
- `ReviewService`: 复习 session、队列、提交、撤销和持久化。
- `AISchedulerDecisionService`: 可选 AI/RL 调度建议、校验和 fallback。
- `ActivityService`: 学习事件和卡片活动。
- `AIPluginHostService`: 启动、探测和调用本地插件。

## 6. AI 插件怎么读

插件目录：`apps/local-web/plugins/rag-core`

| 目标 | 文件 |
| --- | --- |
| 插件声明 | `plugin.json` |
| 插件 API 入口 | `runtime/app/main.py` |
| 请求/响应合同 | `runtime/app/contracts.py` |
| RAG 生成流程 | `runtime/app/pipeline_service.py` |
| 调度建议逻辑 | `runtime/app/scheduler_core.py` |
| vendored RAG 管线 | `runtime/vendor/textbook_qa` |

插件能力：

- `rag.generate_cards`
- `evaluation.score_explanation`
- `scheduler.plan_review`

插件输出必须被后端校验后才能进入持久化层。调度插件尤其要保持克制：它只影响长期间隔，不直接修改当天队列、撤销状态或用户评分语义。

## 7. 关键数据流

RAG 导入：

```text
frontend/features/library/rag-import-dialog.tsx
  -> POST /api/ai/rag/import-cards
  -> backend/app/api/routes/ai.py
  -> RAGImportService
  -> AIPluginHostService / plugin_client.py
  -> rag-core /tasks/rag.generate_cards
  -> SQLite: Deck, Card, KnowledgeUnit
```

理解评估：

```text
frontend/features/evaluation/evaluation-form.tsx
  -> backend/app/api/routes/evaluations.py
  -> EvaluationService
  -> rag-core /tasks/evaluation.score_explanation
  -> LearningEvent
```

复习调度：

```text
frontend/pages/review-page.tsx
  -> backend/app/api/routes/review.py
  -> ReviewService
  -> BasicSessionScheduler
  -> AISchedulerDecisionService when scheduler_mode = ai_rl
  -> CardReviewState + ReviewLog
```

## 8. 适合新手的修改入口

推荐：

- 改文案：`frontend/src/i18n/locales/en.json` 和 `zh.json`。
- 改小 UI：`frontend/src/components/ui` 或局部 `features` 组件。
- 补测试：从 `backend/tests/test_health.py`、`frontend/src/components/ui/ui-primitives.test.tsx` 开始。
- 读一条 API 链路：从前端页面追到 `api`，再追到后端 route 和 service。

谨慎：

- `backend/app/services/review_service.py`
- `backend/app/services/ai_scheduler_decision_service.py`
- `backend/app/db/models.py`
- `backend/alembic/versions`
- `desktop/src-tauri`
- `plugins/rag-core/runtime/vendor/textbook_qa`

这些区域涉及状态一致性、迁移兼容、桌面运行时或 AI 质量，改动前先跑相关测试。

## 9. 常用命令

后端：

```powershell
cd apps/local-web/backend
conda env create -f environment.yml
conda activate ai-memory-card-backend
uvicorn app.main:app --reload
```

前端：

```powershell
cd apps/local-web/frontend
npm install
npm run dev
```

插件测试：

```powershell
cd apps/local-web/plugins/rag-core
pytest tests runtime/tests -q
```

桌面：

```powershell
cd apps/local-web/desktop
npm install
npm run doctor
npm run dev
```

完整开发验证：

```powershell
pytest apps/local-web/backend/tests -q

cd apps/local-web/frontend
npm.cmd test
npm.cmd run build

cd ../plugins/rag-core
pytest tests runtime/tests -q
```

## 10. 本次公开仓库整理做了什么

- 删除研究实验输出、论文材料、缓存、临时数据库和本地运行时目录。
- 删除旧的重复后端 `app/modules` 服务。
- 删除未挂载的早期前端组件。
- 保留 `apps/local-web` 作为正式应用 workspace，避免破坏现有启动和发布脚本。
- 新增 `AISchedulerDecisionService`，把 AI/RL 调度建议从 `ReviewService` 中拆出。
- 将公开项目名和包名统一为 `AI Memory Card` / `ai-memory-card-*`。
- 新增 `docs/development.md` 和 GitHub Actions CI。
