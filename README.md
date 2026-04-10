# Jellyfish AI短剧工厂 / AI Short Drama Studio

<p align="center">
  <img src="./docs/img/logo.svg" alt="Jellyfish Logo" width="160" />
</p>

<p align="center">
  <a href="https://www.apache.org/licenses/LICENSE-2.0">
    <img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License" />
  </a>
  <a href="https://img.shields.io/badge/frontend-React%20%2B%20Vite-61DAFB">
    <img src="https://img.shields.io/badge/frontend-React%20%2B%20Vite-61DAFB" alt="Frontend" />
  </a>
  <a href="https://img.shields.io/badge/backend-FastAPI-009688">
    <img src="https://img.shields.io/badge/backend-FastAPI-009688" alt="Backend" />
  </a>
  <a href="https://github.com/Forget-C/Jellyfish/actions/workflows/deploy-site.yml">
    <img src="https://github.com/Forget-C/Jellyfish/actions/workflows/deploy-site.yml/badge.svg" alt="Deploy Site" />
  </a>
  <a href="https://github.com/Forget-C/Jellyfish/actions/workflows/ghcr-images.yml">
    <img src="https://github.com/Forget-C/Jellyfish/actions/workflows/ghcr-images.yml/badge.svg" alt="Build and push images" />
  </a>
</p>

<p align="center">
  <a href="./README.md">简体中文</a> ·
  <a href="./docs/README.en.md">English</a>
</p>

一站式 AI 生成短剧（竖屏短剧 / 微短剧）的生产工具  
从剧本输入 → 智能分镜 → 角色/场景/道具一致性管理 → AI 视频生成 → 后期剪辑 → 一键导出成片

## 📷 项目截图 / Screenshots

| 项目概览 | 资产管理 |
| --- | --- |
| <img src="./docs/img/project.png" alt="项目概览 / Project Overview" width="420" /> | <img src="./docs/img/%E8%B5%84%E4%BA%A7%E7%AE%A1%E7%90%86.png" alt="资产管理 / Asset Management" width="420" /> |

## ✨ 核心价值

- **把短剧生产流程串起来**：从剧本输入、分镜拆解、镜头准备，到图片/视频生成与任务追踪，尽量减少工具切换和流程割裂
- **把 AI 结果变成可确认、可复用的生产资料**：先沉淀为分镜、候选资产、对白、提示词和生成任务，再进入后续制作
- **把“一致性”作为核心问题来处理**：通过角色、场景、道具、服装等实体管理和镜头级关联，尽量降低人物漂移和场景跑偏
- **把长耗时生成变成可追踪的任务系统**：统一管理文本处理、图片生成、视频生成等异步任务，支持状态可见、可取消、可恢复
- **把 AI 能力接入做成基础设施**：通过模型管理、提示词模板、OpenAPI 协作和任务执行体系，为后续扩展更多工作流留出空间

## ✨ 核心能力

Jellyfish 不是单点的“AI 出图 / AI 出视频”工具，而是一套面向短剧生产的工作台。  
它围绕“剧本理解、分镜准备、资产一致性、生成执行、任务追踪”构建了一条可落地的主流程。

### 1. AI 剧本理解与分镜拆解

支持将章节剧本交给 AI 进行结构化处理，形成后续制作可用的分镜基础数据，包括：

- 剧本拆分为镜头
- 角色 / 场景 / 道具 / 服装等要素提取
- 对白提取与整理
- 剧本优化、简化与一致性检查
- 角色画像、场景信息、道具信息等专项分析

### 2. 分镜准备与确认工作流

当前主流程是：

`剧本拆分 → 分镜准备 → 候选确认 → 镜头 ready → 进入生成工作台`

在准备阶段，支持：

- 提取并刷新镜头候选信息
- 确认或忽略资产候选
- 接受或忽略对白候选
- 关联已有角色 / 场景 / 道具 / 服装
- 对单镜头基础信息进行修正
- 用统一状态判断镜头是否完成准备

### 3. 资产一致性与复用体系

围绕短剧生产中的一致性问题，项目提供统一实体管理能力，覆盖角色、演员、场景、道具和服装。  
支持实体库管理、镜头级关联、图片管理和复用，尽量减少跨镜头生成时的内容漂移。

### 4. 镜头级图片与视频生成编排

在镜头进入 `ready` 后，可继续进入生成工作台完成生成准备与执行，包括：

- 关键帧与参考图管理
- 镜头级视频提示词预览
- 图片 / 视频生成任务发起
- 单镜头与批量生成前检查
- 生成结果回流到镜头与素材体系

### 5. 统一任务中心与异步执行能力

当前支持：

- 文本处理任务异步执行
- 图片 / 视频任务异步执行
- 任务状态、结果、耗时统一追踪
- 取消任务
- 全局任务中心查看运行中与最近完成任务
- 从任务回到对应项目 / 章节 / 镜头上下文

### 6. 模型、提示词与生成基础设施

项目还提供支撑 AI 生产的基础设施能力，包括：

- 多 Provider / 多模型管理
- 模型分类与默认模型设置
- 提示词模板管理
- 文件与生成素材管理
- OpenAPI 驱动的前后端接口协作

## 🚀 主要功能一览

### 项目与章节管理

- 创建和管理项目、章节
- 以章节为单位承载剧本、分镜与生成流程
- 提供基础统计与工作台入口

### AI 剧本处理

- 将章节剧本拆分为多个镜头
- 提取角色、场景、道具、服装与对白信息
- 支持剧本优化、简化与一致性检查
- 支持角色画像、场景信息、道具信息等专项分析

### 分镜准备工作流

- 编辑镜头标题、摘要和基础信息
- 提取并刷新资产/对白候选
- 确认、忽略或关联候选项
- 通过统一准备态判断镜头是否完成确认
- 明确区分“准备完成”和“生成中”

### 资产与实体管理

- 管理角色、演员、场景、道具、服装等实体
- 支持镜头级关联与复用
- 支持实体图片管理
- 支持名称存在性检查，辅助复用已有资产

### 镜头生成工作台

- 管理关键帧、参考图与视频提示词
- 检查镜头视频生成准备度
- 发起图片 / 视频生成任务
- 支持单镜头和批量推进生成流程

### 任务中心

- 统一查看运行中与最近完成的任务
- 跟踪任务状态、进度、耗时与结果
- 支持取消任务
- 支持从任务快速回到对应项目、章节或镜头

### 模型与提示词基础设施

- 管理 Provider、Model 与默认模型设置
- 管理图片、视频、分镜等提示词模板
- 通过 OpenAPI 生成前端请求与类型
- 为后续扩展更多 AI 工作流提供统一底座

### 文件与素材管理

- 管理上传文件与生成产物
- 统一预览、关联和复用图片/视频素材
- 为镜头和实体提供可回溯的素材支撑

## 🎯 适用场景

- 短剧/微短剧内容创作者
- AI 影视工作室批量生产
- 个人创作者想低成本试水竖屏短剧
- 教育/培训机构制作教学短视频
- 品牌/电商制作带剧情的产品宣传短片

## 🛠 技术栈（示例）

- 前端：React 18 + TypeScript + Vite + Ant Design / Tailwind CSS
- 状态管理：Redux Toolkit / Zustand
- 工作流编辑：React Flow
- 视频播放器：Video.js / Plyr
- 富文本/代码编辑：Monaco Editor / React Quill
- 后端（可选开源部分）：Node.js / NestJS / FastAPI / Spring Boot
- AI 生成层：对接多种大模型 API（OpenAI / Anthropic / Midjourney / Runway / Kling / Luma 等）

## 🔁 前端 OpenAPI 请求/类型生成与更新

前端请求函数与数据结构由后端 OpenAPI 文档生成，生成目录为 `front/src/services/generated/`，OpenAPI 文档缓存为 `front/openapi.json`。

在后端开发服务已启动（默认 `http://127.0.0.1:8000`）时，在前端目录执行：

```bash
cd front
pnpm run openapi:update
```

说明：

- `openapi:update` 会先拉取 `http://127.0.0.1:8000/openapi.json` 到 `front/openapi.json`，再生成代码到 `front/src/services/generated/`
- 如需修改请求基础地址，可配置 `VITE_BACKEND_URL`（构建时）或在部署时通过 `BACKEND_URL` 运行时注入（`front/index.html` 引入 `/env.js`），见 `front/src/services/openapi.ts`

## 🐳 Docker 一键启动（MySQL + Redis + RustFS + Backend + Celery Worker + Front）

项目已提供开箱即用的 compose 编排，文件位于 `deploy/compose/`。

### 端口

- 前端：`http://localhost:7788`
- 后端：`http://localhost:8000`（`/docs` 为 Swagger）
- MySQL：`localhost:${MYSQL_PORT:-3306}`
- Redis：`localhost:${REDIS_PORT:-6379}`
- RustFS（S3 API）：`http://localhost:${RUSTFS_PORT:-9000}`（Console：`http://localhost:${RUSTFS_CONSOLE_PORT:-9001}`）

### 启动

```bash
cp deploy/compose/.env.example deploy/compose/.env
docker compose --env-file deploy/compose/.env -f deploy/compose/docker-compose.yml up --build
```

首次启动会自动运行一次 `backend/init_db.py` 创建表结构（`backend-init-db` 服务）。
并在其成功后自动按文件名前缀顺序依次导入 `backend/sql/` 下的 SQL 文件（`mysql-init-sql` 服务），例如：

- `001-init-prompt-template.sql`
- `002-add-shot-extracted-candidates.sql`

另外，compose 还会启动：

- `redis`
  - 作为 Celery broker
- `celery-worker`
  - 负责执行 `divide / extract` 等长耗时任务

### Redis / Celery Broker 配置

compose 环境变量中可单独配置 Redis：

- `REDIS_PORT`
- `REDIS_DB`
- `REDIS_PASSWORD`

如果**未显式设置** `CELERY_BROKER_URL`，后端会自动按以下规则拼接：

```text
redis://[:password@]REDIS_HOST:REDIS_PORT/REDIS_DB
```

在 compose 场景下默认使用：

```text
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=${REDIS_DB:-0}
```

### Celery 首轮联调检查

完成启动后，建议优先验证：

1. `redis` 为 `healthy`
2. `celery-worker` 日志中出现 `ready`
3. 触发：
   - 分镜管理页的 `一键提取分镜`
   - 分镜编辑页的 `提取并刷新候选`
4. 页面刷新后继续查看：
   - 章节详情
   - 分镜列表
   - `/api/v1/film/tasks/{task_id}/status`

联调成功的核心判断标准：

- `divide / extract` 任务由 `celery-worker` 承担主要耗时执行
- `backend` 仍然能继续响应其他接口
- 页面刷新后任务状态仍能恢复

## 🧑‍💻 开发环境启动（前后端分离）

### 端口

- 前端（Vite dev）：`http://localhost:7788`
- 后端（FastAPI）：`http://localhost:8000`（`/docs` 为 Swagger）

### 启动后端

```bash
cd backend
cp .env.example .env
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

提交前可在 `backend` 目录执行 `uv sync --group dev` 与 `uv run pylint app` 做静态检查（配置与说明见 [backend/README.md](backend/README.md)）。

### 启动前端

```bash
cd front
pnpm install
pnpm dev
```

### （可选）仅启动依赖服务 MySQL + Redis + RustFS

如果你希望开发时使用 MySQL + Redis + RustFS（而不是默认 SQLite），可以只启动基础设施服务：

```bash
cp deploy/compose/.env.example deploy/compose/.env
docker compose --env-file deploy/compose/.env -f deploy/compose/docker-compose.yml up -d mysql redis rustfs
```

### Git 提交说明格式

本地提交时，**首行**须符合：`[类型] 摘要`。`类型` 只能是下列**枚举之一**（**必须小写**），后接**一个空格**再写摘要：

| 类型 | 含义 |
|------|------|
| `feat` | 新功能 |
| `fix` | 缺陷 / Bug 修复 |
| `docs` | 文档 |
| `style` | 格式调整（不改变代码含义） |
| `refactor` | 重构 |
| `perf` | 性能优化 |
| `test` | 测试 |
| `chore` | 杂项 / 工具 / 非 src |
| `ci` | CI 配置 |
| `build` | 构建系统或依赖 |
| `revert` | 回滚 |

示例：`[feat] 新功能`、`[fix] 修复登录`、`[docs] 更新 README`。不可使用未在表中的类型（如 `[wip]`、`[update]`）。

启用校验（在本仓库根目录执行一次即可）：

```bash
git config core.hooksPath .githooks
```

说明：合并提交（`Merge …`）、`Revert …` 及合并流程中的提交会被钩子放行。

**远端强制**：向默认分支发起的 Pull Request 会由 [`.github/workflows/commit-messages.yml`](.github/workflows/commit-messages.yml) 校验 PR 内每个提交的标题行（规则与上相同；`Merge` / `Revert` 开头跳过）。请在分支上把提交信息写成符合规范的格式后再推。

## 🚧 开发状态 / Roadmap

项目处于**活跃开发中**，以下为当前功能完成度与规划进度。欢迎通过 [Issues](https://github.com/Forget-C/Jellyfish/issues) 参与讨论与贡献。

### ✅ 已完成

| 模块 | 说明 |
|------|------|
| 模型管理交互 | 模型列表、筛选、配置等前端交互已就绪 |
| 项目管理交互 | 项目创建、编辑、仪表盘等交互流程已打通 |
| 项目工作台交互 | 项目级工作台布局与基础操作已实现 |
| 章节拍摄工作台交互 | 章节拍摄相关界面与交互已就绪 |
| 模型管理功能 | 多供应商、多类型模型的管理与默认配置 |
| 项目管理功能 | 项目 CRUD、全局风格与种子等配置能力 |

### 🚧 进行中 / 规划中

| 模块 | 说明 |
|------|------|
| 章节拍摄工作台 | 完整分镜编辑、视频生成与预览流程（功能深化中） |
| 高级提示词 | 分镜/角色/场景等高级提示词模板与智能填充（规划中） |

## 开发者

项目仍处于开发阶段，核心流程与数据模型尚未完全稳定；但已提供基于 Docker Compose 的本地启动方式（见上方）。

## 📄 开源协议 / License

本项目采用 [Apache-2.0](LICENSE) 开源协议。  
欢迎提交 **Pull Request**、**Issue** 与 **Star**，与社区一起把 AI 短剧生产工具做成可落地的行业方案。

## 💬 交流与反馈 / Community

- **[GitHub Issues](https://github.com/Forget-C/Jellyfish/issues)** — 功能建议、Bug 反馈、使用讨论
- **微信群 / Discord** — 待建设，后续会在本页更新入口
