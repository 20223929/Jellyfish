# 生成准备架构

## 定位

Jellyfish 当前已经将多条生成链逐步收敛到统一的“生成准备”模型，用于解决以下问题：

- 基础真值与最终提交内容混用
- 预览与提交使用的上下文不一致
- 页面内部状态散落，`stale / loading / submit` 语义混乱

当前已接入该架构的链路包括：

1. 分镜帧图片生成
2. 视频提示词预览与提交
3. 资产图片生成（角色 / 演员 / 场景 / 道具 / 服装）

## 统一模型

当前统一使用 4 层结构：

1. `Base Draft`
   - 可持久化、可编辑的业务真值
2. `Context`
   - 本次生成依赖的动态上下文
3. `Derived Preview`
   - 基于 `Base Draft + Context` 推导出的预览结果
4. `Submission Payload`
   - 最终提交给模型的运行载荷

## 后端当前结构

当前统一服务目录位于：

```text
backend/app/services/studio/generation/
├── shared/
├── frame/
├── video/
└── asset_image/
```

### `shared`

负责放置生成准备的共享类型：

- `GenerationBaseDraft`
- `GenerationContext`
- `GenerationDerivedPreview`
- `GenerationSubmissionPayload`

### `frame`

当前关键帧图片链已经按以下职责拆分：

- `build_base`
- `build_context`
- `derive_preview`
- `build_submission`

当前 API 仍保持原路径不变，但内部已经开始调用这一层服务。

### `video`

当前视频链已经开始使用同样的四段式结构：

- `build_base`
- `build_context`
- `derive_preview`
- `build_submission`

当前 `preview-prompt` 与 `create video task` 已共享同一份 `reference_mode + images` 上下文。

当前视频参数已收口为以 `ratio` 为唯一业务主参数：

- 项目级默认：`Project.default_video_ratio`
- 分镜级覆盖：`ShotDetail.override_video_ratio`
- 前端在提交视频任务时显式传入本次生效的 `ratio`
- 后端直接使用请求中的 `ratio` 创建任务
- 若某个供应商不直接支持 `ratio`，由 provider adapter 在执行层内部派生辅助 `size`
- 前端比例枚举来自当前默认视频模型 capability 动态返回，不再使用静态常量
- 关键帧图片若用于视频参考，提交时会显式携带 `target_ratio + resolution_profile`
- 后端根据当前默认图片模型 capability 解析对应 `size`，保证关键帧画幅与目标视频保持一致
- 工作室会展示当前关键帧规格预览：`ratio + resolution_profile -> size`

### `asset_image`

当前资产图片生成已开始迁移到：

- `build_base`
- `build_context`
- `derive_preview`
- `build_submission`

当前 actor / character / scene / prop / costume 图片的 render / submit 已开始走这套结构。

## 底层渲染组件约定

当前旧的图片兼容层已经移除，新的生成准备编排统一以以下目录为主入口：

- `generation/frame`
- `generation/video`
- `generation/asset_image`

其中仅保留 `shot_video_prompt_pack` 作为视频 pack 与模板渲染的底层组件：

- 它负责构建 `ShotVideoPromptPackRead`
- 它负责模板渲染所需的底层函数
- 它不再承担视频预览 / 提交的主编排入口职责

## 前端当前结构

### `useGenerationDraft`

当前前端已提供统一 hook：

```text
front/src/pages/aiStudio/hooks/useGenerationDraft.ts
```

该 hook 统一管理：

- `base`
- `context`
- `derived`
- `state`
- `deriveNow`
- `submitNow`
- `hydrate`
- `resetDerived`

### 当前已接入页面

#### 分镜工作室

`ChapterStudio` 当前已开始将：

- 关键帧提示词预览
- 视频提示词预览

接入 `useGenerationDraft`，逐步统一为：

- 用户编辑 `base`
- 页面维护 `context`
- 系统展示 `derived`
- 提交前通过 `submitNow()` 自动确保 `derived` 为最新结果

当前关键帧图片生成与视频生成都已经接入这套提交语义：

- 若基础提示词或上下文已变化，会先重新 `derive`
- 再使用最新的 `derived` 结果提交任务
- 页面不再单独维护一套“提交前再手动 render”的旁路逻辑

#### 资产编辑页

`AssetEditPageBase` 当前已开始将资产图片提示词预览与提交接入 `useGenerationDraft`。

因此，角色、演员、场景、道具、服装等资产编辑入口，已共享同一套生成准备心智模型。

其中，角色详情页也已收口到与演员 / 场景 / 道具 / 服装相同的资产编辑入口模型，不再单独维护一套角色图片生成入口逻辑。

当前资产图片生成提交也已统一为：

- 页面维护 `base + context`
- `submitNow()` 在提交前自动保证 `derived` 最新
- 任务创建使用最新的 `derived.prompt + derived.images`
- 调试信息默认收起，仅在用户主动展开时展示上下文与质量校验细节

## 当前边界

### 任务中心

任务中心保持“通用、轻量”的原则：

- 展示任务状态、进度、成功失败、取消与回跳入口
- 不承载业务级上下文摘要
- 不承载提示词调试详情

### 不属于该架构的模块

以下模块当前不属于“生成准备架构”：

1. 脚本处理类任务
2. 分镜编辑页的信息提取确认流
3. 任务中心

这些模块有独立职责，不参与当前的 `Base Draft / Context / Derived Preview / Submission Payload` 收敛。
