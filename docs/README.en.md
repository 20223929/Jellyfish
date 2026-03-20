# Jellyfish — AI Short Drama Studio

<p align="center">
  <img src="./img/logo.svg" alt="Jellyfish Logo" width="160" />
</p>

<p align="center">
  <a href="../README.md">简体中文</a> ·
  <a href="./README.en.md">English</a>
</p>

An end-to-end production tool for AI-generated short dramas (vertical / micro drama).  
From script input → smart storyboarding → character/scene/prop consistency management → AI video generation → post-production editing → one-click export.

## 📷 Screenshots

| Project overview | Asset management |
| --- | --- |
| <img src="./img/project.png" alt="Project overview" width="420" /> | <img src="./img/资产管理.png" alt="Asset management" width="420" /> |

## ✨ Core value

- **Consistency first**: Global seed + unified style + asset reuse to address the main pain of AI generation—character and scene drift.
- **Industrialized workflow**: From narrative script to shootable storyboards to video clips in one closed loop.
- **Visual & controllable**: WYSIWYG storyboard editor + fine-grained shot controls + real-time preview.
- **Asset reuse system**: Full lifecycle management for characters, scenes, props, costumes, and prompt templates.

## 🚀 Key features

| Module | Core capabilities | Highlights |
|--------|-------------------|------------|
| Project management | Create projects, global style/seed control, project dashboard, chapter stats | Global seed to reduce drift, enforced style inheritance |
| Chapter production workspace | Script input → smart condense → storyboard extraction → storyboard edit → video generation → preview | Three-column layout, collapsible right panel, batch operations |
| Storyboard fine controls | Shot size/angle/movement/emotion/duration/atmosphere/dialog/music/SFX/hidden shots | Separate prompts for first/last/key frames, multi-version management |
| Advanced generation controls | Reference images across shots, ControlNet pose/depth, lip-sync, model & duration selection | Controllable motion + lip-sync |
| Asset management | Centralized characters/scenes/props/costumes, smart extraction + manual linking + prompt templates | Per-project vs global asset library |
| Prompt template library | Storyboard/character/scene/video/music/SFX/composite prompt templates | One-click init for new chapters |
| Post-production editing | Timeline editing, multi-track video/audio, asset bin drag-drop, final export | Edit full short dramas directly from AI clips |
| Agent workflows | Custom agents (plot/character extraction, storyboard suggestions), visual orchestration & testing | Node-based workflow editor (Dify-like) |
| Model management | Multi-provider (OpenAI/Claude/Tongyi/Hunyuan, etc.), model types (text/image/video) | Per-type default model, quick connection test |
| Generated media management | Unified image/video preview, tagging, filtering, batch export | Reuse high-quality assets quickly |

## 🎯 Use cases

- Short / micro-drama content creators
- AI film studios for batch production
- Solo creators exploring vertical short drama on a budget
- Education and training teams making teaching videos
- Brands and e-commerce creating story-driven product promos

## 🛠 Tech stack (example)

- Frontend: React 18 + TypeScript + Vite + Ant Design / Tailwind CSS
- State: Redux Toolkit / Zustand
- Workflow editor: React Flow
- Video player: Video.js / Plyr
- Rich text / code editor: Monaco Editor / React Quill
- Backend (optional open-source): Node.js / NestJS / FastAPI / Spring Boot
- AI layer: Multiple model APIs (OpenAI / Anthropic / Midjourney / Runway / Kling / Luma, etc.)

## 🔁 Frontend OpenAPI client & type generation

Request helpers and types are generated from the backend OpenAPI spec. Output directory: `front/src/services/generated/`. Cached spec: `front/openapi.json`.

With the backend dev server running (default `http://127.0.0.1:8000`), from the frontend directory run:

```bash
cd front
pnpm run openapi:update
```

Notes:

- `openapi:update` fetches `http://127.0.0.1:8000/openapi.json` into `front/openapi.json`, then generates code under `front/src/services/generated/`.
- To change the API base URL (default same-origin `/api`), call `initOpenAPI('http://127.0.0.1:8000')` at app bootstrap; see `front/src/services/openapi.ts`.

## 🚧 Development status / Roadmap

The project is **actively developed**. Below is the current completion and planned work. Feedback and contributions via [Issues](https://github.com/your-org/jellyfish/issues) are welcome.

### ✅ Done

| Module | Description |
|--------|-------------|
| Model management UI | Model list, filters, and config UI are in place |
| Project management UI | Project create/edit and dashboard flows are wired |
| Project workspace UI | Project-level workspace layout and basic actions |
| Chapter production workspace UI | Chapter production screens and interactions |
| Model management | Multi-provider, multi-type model management and default config |
| Project management | Project CRUD, global style and seed configuration |

### 🚧 In progress / Planned

| Module | Description |
|--------|-------------|
| Chapter production workspace | Full storyboard editing, video generation, and preview (deepening features) |
| Advanced prompts | Advanced prompt templates and smart fill for storyboard/character/scene (planned) |

## Developer

The project is still under development. Core workflows and data models have not yet stabilized. For now, we do not provide a deployment option, and we have temporarily paused PR submissions. We plan to reopen after the beta release in early April.

## 📄 Open-source License / License

This project is licensed under [Apache-2.0](../LICENSE).  
We welcome Pull Requests, Issues, and Stars, and we will work with the community to turn this AI short drama production tool into a practical, industry-ready solution.

## 💬 Community & feedback

- **[GitHub Issues](https://github.com/your-org/jellyfish/issues)** — Feature suggestions, bug reports, and usage discussions
- **WeChat / Discord** — To be set up; we will update the entry on this page later
