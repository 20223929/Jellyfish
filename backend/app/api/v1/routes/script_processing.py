"""脚本处理 API 接口：分镜、信息提取、实体合并、变体分析、一致性检查、输出编译。"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chains.agents import (
    CharacterPortraitAnalysisAgent,
    CostumeInfoAnalysisAgent,
    ScriptDividerAgent,
    ElementExtractorAgent,
    EntityMergerAgent,
    VariantAnalyzerAgent,
    ConsistencyCheckerAgent,
    PropInfoAnalysisAgent,
    SceneInfoAnalysisAgent,
    ScriptOptimizerAgent,
    ScriptSimplifierAgent,
)
from app.chains.agents.script_processing_agents import (
    ScriptDivisionResult,
    EntityMergeResult,
    VariantAnalysisResult,
    ScriptConsistencyCheckResult,
    ScriptOptimizationResult,
    ScriptSimplificationResult,
    StudioScriptExtractionDraft,
)
from app.dependencies import get_db, get_llm, get_nothinking_llm
from app.models.studio import CameraAngle, CameraMovement, CameraShotType, Chapter, Shot, ShotDetail, VFXType
from app.schemas.common import ApiResponse, success_response
from app.schemas.skills.character_portrait import CharacterPortraitAnalysisResult
from app.schemas.skills.costume_info_analysis import CostumeInfoAnalysisResult
from app.schemas.skills.prop_info_analysis import PropInfoAnalysisResult
from app.schemas.skills.scene_info_analysis import SceneInfoAnalysisResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/script-processing", tags=["script-processing"])


# ============================================================================
# 1. ScriptDividerAgent - 剧本分镜
# ============================================================================

class ScriptDividerRequest(BaseModel):
    """剧本分镜请求。"""
    script_text: str = Field(..., description="完整剧本文本", min_length=1)
    write_to_db: bool = Field(False, description="是否将分镜写入数据库（AI Studio shots 表）")
    chapter_id: str | None = Field(
        None,
        description="章节 ID（write_to_db=true 时必填）",
        min_length=1,
    )


@router.post(
    "/divide",
    response_model=ApiResponse[ScriptDivisionResult],
    summary="将剧本分割为多个镜头",
    description=(
        "输入完整剧本文本，输出分镜列表（index/start_line/end_line/script_excerpt/"
        "shot_name/time_of_day）。"
        "注意：此阶段不强制稳定ID，角色以“称呼/名字”弱信息输出，稳定ID在合并阶段统一分配。"
    )
)
async def divide_script(
    request: ScriptDividerRequest,
    llm: BaseChatModel = Depends(get_nothinking_llm),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ScriptDivisionResult]:
    """
    将完整剧本文本自动分割为多个镜头。
    
    请求体：
    - script_text: 完整剧本文本
    
    返回：ScriptDivisionResult
    - shots: 分镜列表，包含每个镜头的 index、起止行号、shot_name、script_excerpt、time_of_day
    - total_shots: 总镜头数
    - notes: 拆分说明（可选）
    """
    try:
        agent = ScriptDividerAgent(llm)
        result = agent.divide_script(script_text=request.script_text)

        if request.write_to_db:
            if not request.chapter_id:
                raise HTTPException(status_code=400, detail="chapter_id is required when write_to_db=true")

            chapter = await db.get(Chapter, request.chapter_id)
            if chapter is None:
                raise HTTPException(status_code=400, detail="Chapter not found")

            existing = await db.execute(
                select(Shot.id).where(Shot.chapter_id == request.chapter_id).limit(1)
            )
            if existing.first() is not None:
                raise HTTPException(
                    status_code=400,
                    detail="Chapter already has shots; refusing to write (write_strategy=fail)",
                )

            for s in result.shots:
                title = (s.shot_name or "").strip() or f"镜头 {s.index}"
                shot_id = str(uuid.uuid4())
                db.add(
                    Shot(
                        id=shot_id,
                        chapter_id=request.chapter_id,
                        index=s.index,
                        title=title,
                        script_excerpt=s.script_excerpt,
                    )
                )
                db.add(
                    ShotDetail(
                        id=shot_id,
                        camera_shot=CameraShotType.ms,
                        angle=CameraAngle.eye_level,
                        movement=CameraMovement.static,
                        follow_atmosphere=True,
                        vfx_type=VFXType.none,
                        duration=4,
                    )
                )
            # 触发唯一约束/外键检查，确保在返回前失败
            await db.flush()

        return success_response(data=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Script dividing failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to divide script: {str(e)}"
        )


# ============================================================================
# 2. EntityMergerAgent - 实体合并
# ============================================================================

class EntityMergerRequest(BaseModel):
    """实体合并请求。"""
    all_shot_extractions: list[dict[str, Any]] = Field(
        ...,
        description="所有镜头提取结果（ShotElementExtractionResult 的序列化形式）"
    )
    historical_library: dict[str, Any] | None = Field(
        None,
        description="历史实体库（可选，用于增量合并）"
    )
    script_division: dict[str, Any] | None = Field(
        None,
        description="脚本分镜结果（可选；ScriptDivisionResult 序列化），用于定位与统计",
    )
    previous_merge: dict[str, Any] | None = Field(
        None,
        description="上一次合并结果（可选；EntityMergeResult 序列化），用于冲突重试合并",
    )
    conflict_resolutions: list[dict[str, Any]] | None = Field(
        None,
        description="冲突解决建议列表（可选；用于冲突重试合并）",
    )


@router.post(
    "/merge-entities",
    response_model=ApiResponse[EntityMergeResult],
    summary="合并多镜头的实体信息",
    description=(
        "输入全部分镜提取结果（可选带上脚本分镜与历史实体库），输出合并后的实体库："
        "角色库/地点库/场景库/道具库（静态画像 + 变体列表）。"
        "该步骤会统一分配稳定ID（如 char_001/loc_001/prop_001/scene_001）。"
        "当提供 previous_merge 与 conflict_resolutions 时，将进行冲突重试合并，优先消解 conflicts 并尽量保持 ID 稳定。"
    )
)
async def merge_entities(
    request: EntityMergerRequest,
    llm: BaseChatModel = Depends(get_llm),
) -> ApiResponse[EntityMergeResult]:
    """
    将多个镜头的提取结果合并，统一实体定义。
    
    请求体：
    - all_shot_extractions: 所有镜头的提取结果
    - historical_library: 历史实体库（可选，用于增量更新）
    - script_division: 脚本分镜结果（可选，用于定位与统计）
    - previous_merge: 上一次合并结果（可选；用于冲突重试合并）
    - conflict_resolutions: 冲突解决建议列表（可选；用于冲突重试合并）
    
    返回：EntityMergeResult
    - merged_library: 合并后的实体库（characters/locations/scenes/props，含 variants）
    - merge_stats: 合并统计信息
    - conflicts: 发现的冲突/待处理项
    - notes: 合并说明（可选）
    """
    try:
        agent = EntityMergerAgent(llm)
        result = agent.extract(
            all_extractions_json=json.dumps(request.all_shot_extractions, ensure_ascii=False),
            historical_library_json=json.dumps(request.historical_library or {}, ensure_ascii=False),
            script_division_json=json.dumps(request.script_division or {}, ensure_ascii=False),
            previous_merge_json=json.dumps(request.previous_merge or {}, ensure_ascii=False),
            conflict_resolutions_json=json.dumps(request.conflict_resolutions or [], ensure_ascii=False),
        )
        return success_response(data=result)
    except Exception as e:
        logger.error(f"Entity merging failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to merge entities: {str(e)}"
        )


# ============================================================================
# 4. VariantAnalyzerAgent - 变体分析
# ============================================================================

class VariantAnalysisRequest(BaseModel):
    """变体分析请求。"""
    merged_library: dict[str, Any] = Field(
        ...,
        description="合并后的实体库（EntityLibrary 的序列化形式；来自 EntityMerger 输出的 merged_library）"
    )
    all_shot_extractions: list[dict[str, Any]] = Field(
        ...,
        description="所有镜头提取结果"
    )
    script_division: dict[str, Any] | None = Field(
        None,
        description="脚本分镜结果（可选；ScriptDivisionResult 序列化），用于章节/段落分组",
    )


@router.post(
    "/analyze-variants",
    response_model=ApiResponse[VariantAnalysisResult],
    summary="分析服装/外形变体",
    description="检测角色服装/外形变化，构建演变时间线，生成章节变体建议列表与变体建议。"
)
async def analyze_variants(
    request: VariantAnalysisRequest,
    llm: BaseChatModel = Depends(get_llm),
) -> ApiResponse[VariantAnalysisResult]:
    """
    分析实体的变体（特别是角色服装变化）。
    
    请求体：
    - merged_library: 合并后的实体库
    - all_shot_extractions: 所有镜头提取结果
    - script_division: 脚本分镜结果（可选，用于章节/段落分组）
    
    返回：VariantAnalysisResult
    - costume_timelines: 各角色的服装演变时间线
    - variant_suggestions: 变体建议列表
    - chapter_variants: 按章节整理的变体信息
    - notes: 分析说明（可选）
    """
    try:
        agent = VariantAnalyzerAgent(llm)
        result = agent.extract(
            merged_library_json=json.dumps(request.merged_library, ensure_ascii=False),
            all_extractions_json=json.dumps(request.all_shot_extractions, ensure_ascii=False),
            script_division_json=json.dumps(request.script_division or {}, ensure_ascii=False),
        )
        return success_response(data=result)
    except Exception as e:
        logger.error(f"Variant analysis failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze variants: {str(e)}"
        )


# ============================================================================
# 5. ConsistencyCheckerAgent - 一致性检查（新流程：基于原文）
# ============================================================================

class ScriptConsistencyCheckRequest(BaseModel):
    """一致性检查请求（角色混淆）。"""
    script_text: str = Field(..., description="完整剧本文本", min_length=1)


@router.post(
    "/check-consistency",
    response_model=ApiResponse[ScriptConsistencyCheckResult],
    summary="检查角色混淆一致性（基于原文）",
    description="检测同一角色在不同段落/镜头被赋予不同身份/行为主体导致混淆，并给出修改建议。"
)
async def check_consistency(
    request: ScriptConsistencyCheckRequest,
    llm: BaseChatModel = Depends(get_llm),
) -> ApiResponse[ScriptConsistencyCheckResult]:
    """
    检查实体定义与分镜内容的一致性。
    
    请求体：
    - script_text: 完整剧本文本
    
    返回：ScriptConsistencyCheckResult
    - issues: 角色混淆问题列表（含 description/suggestion/affected_lines）
    - has_issues: 是否发现问题
    - summary: 总结（可选）
    """
    try:
        agent = ConsistencyCheckerAgent(llm)
        result = agent.extract(script_text=request.script_text)
        return success_response(data=result)
    except Exception as e:
        logger.error(f"Consistency checking failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check consistency: {str(e)}"
        )


# ============================================================================
# 5b. CharacterPortraitAnalysisAgent - 人物画像缺失信息分析
# ============================================================================
class CharacterPortraitAnalysisRequest(BaseModel):
    """人物画像缺失信息分析请求。"""

    character_context: str | None = Field(
        None,
        description="原文人物上下文（可为空；用于提供额外背景，帮助判断缺失信息）",
    )
    character_description: str = Field(..., description="原文人物描述", min_length=1)


@router.post(
    "/analyze-character-portrait",
    response_model=ApiResponse[CharacterPortraitAnalysisResult],
    summary="分析人物画像缺失信息",
    description="根据原文人物上下文与人物描述，判断缺少哪些关键信息，并给出优化后的人物画像描述。",
)
async def analyze_character_portrait(
    request: CharacterPortraitAnalysisRequest,
    llm: BaseChatModel = Depends(get_llm),
) -> ApiResponse[CharacterPortraitAnalysisResult]:
    try:
        agent = CharacterPortraitAnalysisAgent(llm)
        result = agent.analyze_character_description(
            character_context=request.character_context,
            character_description=request.character_description,
        )
        return success_response(data=result)
    except Exception as e:
        logger.error(f"Character portrait analysis failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze character portrait: {str(e)}",
        )


# ============================================================================
# 5c. PropInfoAnalysisAgent - 道具信息缺失分析
# ============================================================================
class PropInfoAnalysisRequest(BaseModel):
    """道具信息缺失分析请求。"""

    prop_context: str | None = Field(
        None,
        description="原文道具上下文（可为空；用于提供额外背景，帮助判断缺失信息）",
    )
    prop_description: str = Field(..., description="原文道具描述", min_length=1)


@router.post(
    "/analyze-prop-info",
    response_model=ApiResponse[PropInfoAnalysisResult],
    summary="分析道具信息缺失项",
    description="根据原文道具上下文与道具描述，判断缺少哪些关键信息，并给出优化后的可生成道具描述。",
)
async def analyze_prop_info(
    request: PropInfoAnalysisRequest,
    llm: BaseChatModel = Depends(get_llm),
) -> ApiResponse[PropInfoAnalysisResult]:
    try:
        agent = PropInfoAnalysisAgent(llm)
        result = agent.analyze_prop_description(
            prop_context=request.prop_context,
            prop_description=request.prop_description,
        )
        return success_response(data=result)
    except Exception as e:
        logger.error(f"Prop info analysis failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze prop info: {str(e)}",
        )


# ============================================================================
# 5d. SceneInfoAnalysisAgent - 场景信息缺失分析
# ============================================================================
class SceneInfoAnalysisRequest(BaseModel):
    """场景信息缺失分析请求。"""

    scene_context: str | None = Field(
        None,
        description="原文场景上下文（可为空；用于提供额外背景，帮助判断缺失信息）",
    )
    scene_description: str = Field(..., description="原文场景描述", min_length=1)


@router.post(
    "/analyze-scene-info",
    response_model=ApiResponse[SceneInfoAnalysisResult],
    summary="分析场景信息缺失项",
    description="根据原文场景上下文与场景描述，判断缺少哪些关键信息，并给出优化后的可生成场景描述。",
)
async def analyze_scene_info(
    request: SceneInfoAnalysisRequest,
    llm: BaseChatModel = Depends(get_llm),
) -> ApiResponse[SceneInfoAnalysisResult]:
    try:
        agent = SceneInfoAnalysisAgent(llm)
        result = agent.analyze_scene_description(
            scene_context=request.scene_context,
            scene_description=request.scene_description,
        )
        return success_response(data=result)
    except Exception as e:
        logger.error(f"Scene info analysis failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze scene info: {str(e)}",
        )


# ============================================================================
# 5e. CostumeInfoAnalysisAgent - 服装信息缺失分析
# ============================================================================
class CostumeInfoAnalysisRequest(BaseModel):
    """服装信息缺失分析请求。"""

    costume_context: str | None = Field(
        None,
        description="原文服装上下文（可为空；用于提供额外背景，帮助判断缺失信息）",
    )
    costume_description: str = Field(..., description="原文服装描述", min_length=1)


@router.post(
    "/analyze-costume-info",
    response_model=ApiResponse[CostumeInfoAnalysisResult],
    summary="分析服装信息缺失项",
    description="根据原文服装上下文与服装描述，判断缺少哪些关键信息，并给出优化后的可生成服装描述。",
)
async def analyze_costume_info(
    request: CostumeInfoAnalysisRequest,
    llm: BaseChatModel = Depends(get_llm),
) -> ApiResponse[CostumeInfoAnalysisResult]:
    try:
        agent = CostumeInfoAnalysisAgent(llm)
        result = agent.analyze_costume_description(
            costume_context=request.costume_context,
            costume_description=request.costume_description,
        )
        return success_response(data=result)
    except Exception as e:
        logger.error(f"Costume info analysis failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze costume info: {str(e)}",
        )


# ============================================================================
# 6. ScriptOptimizerAgent - 剧本优化（非主线，按需触发）
# ============================================================================

class ScriptOptimizeRequest(BaseModel):
    """剧本优化请求（基于一致性检查结果）。"""
    script_text: str = Field(..., description="原文剧本文本", min_length=1)
    consistency: dict[str, Any] = Field(..., description="一致性检查输出（ScriptConsistencyCheckResult 序列化）")


class ScriptSimplifyRequest(BaseModel):
    """智能精简剧本请求。"""

    script_text: str = Field(..., description="原文剧本文本", min_length=1)


@router.post(
    "/optimize-script",
    response_model=ApiResponse[ScriptOptimizationResult],
    summary="基于一致性检查优化剧本",
    description="将一致性检查输出及原文作为输入，生成优化后的剧本（尽量少改，只改与角色混淆 issues 相关段落）。"
)
async def optimize_script(
    request: ScriptOptimizeRequest,
    llm: BaseChatModel = Depends(get_llm),
) -> ApiResponse[ScriptOptimizationResult]:
    """
    输入原文 + 一致性检查输出，生成优化后的剧本。
    """
    try:
        agent = ScriptOptimizerAgent(llm)
        result = agent.extract(
            script_text=request.script_text,
            consistency_json=json.dumps(request.consistency, ensure_ascii=False),
        )
        return success_response(data=result)
    except Exception as e:
        logger.error(f"Script optimization failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to optimize script: {str(e)}"
        )


@router.post(
    "/simplify-script",
    response_model=ApiResponse[ScriptSimplificationResult],
    summary="智能精简剧本",
    description="在保留剧情主体并保证剧情连续的前提下精简剧本文本。",
)
async def simplify_script(
    request: ScriptSimplifyRequest,
    llm: BaseChatModel = Depends(get_llm),
) -> ApiResponse[ScriptSimplificationResult]:
    """输入原文剧本，输出精简后的文本与精简策略摘要。"""
    try:
        agent = ScriptSimplifierAgent(llm)
        result = agent.extract(script_text=request.script_text)
        return success_response(data=result)
    except Exception as e:
        logger.error(f"Script simplification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to simplify script: {str(e)}",
        )


# ============================================================================
# 7. ElementExtractorAgent - 项目级提取（最终输出）
# ============================================================================

class ScriptExtractRequest(BaseModel):
    """项目级信息提取请求（最终输出）。"""
    project_id: str = Field(..., description="项目 ID", min_length=1)
    chapter_id: str = Field(..., description="章节 ID", min_length=1)
    script_division: dict[str, Any] = Field(..., description="分镜结果（ScriptDivisionResult 序列化）")
    consistency: dict[str, Any] | None = Field(None, description="一致性检查结果（可选；ScriptConsistencyCheckResult 序列化）")


@router.post(
    "/extract",
    response_model=ApiResponse[StudioScriptExtractionDraft],
    summary="项目级信息提取（最终输出）",
    description="输入分镜结果（可选带一致性检查结果），输出可导入 Studio 的草稿结构（name-based，ID 由导入接口生成）。"
)
async def extract_script(
    request: ScriptExtractRequest,
    llm: BaseChatModel = Depends(get_nothinking_llm),
) -> ApiResponse[StudioScriptExtractionDraft]:
    try:
        agent = ElementExtractorAgent(llm)
        result = agent.extract(
            project_id=request.project_id,
            chapter_id=request.chapter_id,
            script_division_json=json.dumps(request.script_division, ensure_ascii=False),
            consistency_json=json.dumps(request.consistency or {}, ensure_ascii=False),
        )
        return success_response(data=result)
    except Exception as e:
        logger.error(f"Script extraction failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to extract script: {str(e)}",
        )


# ============================================================================
# 完整工作流 - 一站式处理
# ============================================================================

class FullProcessRequest(BaseModel):
    """完整工作流请求。"""
    script_text: str = Field(..., description="完整剧本文本", min_length=1)
    project_id: str = Field(..., description="项目 ID", min_length=1)
    chapter_id: str = Field(..., description="章节 ID", min_length=1)
    auto_optimize: bool = Field(True, description="发现角色混淆问题时是否自动优化剧本")


@router.post(
    "/full-process",
    response_model=ApiResponse[StudioScriptExtractionDraft],
    summary="完整工作流处理",
    description="新流程：一致性检查→（可选优化）→分镜→项目级信息提取（最终输出）"
)
async def full_process(
    request: FullProcessRequest,
    llm: BaseChatModel = Depends(get_llm),
) -> ApiResponse[StudioScriptExtractionDraft]:
    """
    完整的脚本处理工作流（新流程）：
    1. 一致性检查（角色混淆）
    2. 若发现问题且 auto_optimize=true：剧本优化
    3. 分镜分割
    4. 项目级信息提取（最终输出）
    
    请求体：
    - script_text: 完整剧本文本
    
    返回：OutputCompileResult（最终编译结果）
    """
    try:
        # 1. 一致性检查
        logger.info("Step 1: Consistency check (character confusion)...")
        checker = ConsistencyCheckerAgent(llm)
        consistency = checker.extract(script_text=request.script_text)

        # 2. 可选优化
        script_text = request.script_text
        if request.auto_optimize and consistency.has_issues:
            logger.info("Step 2: Optimizing script...")
            optimizer = ScriptOptimizerAgent(llm)
            optimized = optimizer.extract(
                script_text=request.script_text,
                consistency_json=json.dumps(consistency.model_dump(), ensure_ascii=False),
            )
            if optimized.optimized_script_text.strip():
                script_text = optimized.optimized_script_text

        # 3. 分镜
        logger.info("Step 3: Dividing script...")
        divider = ScriptDividerAgent(llm)
        division = divider.divide_script(script_text=script_text)

        # 4. 项目级提取（最终输出）
        logger.info("Step 4: Project-level extraction...")
        extractor = ElementExtractorAgent(llm)
        final_result = extractor.extract(
            project_id=request.project_id,
            chapter_id=request.chapter_id,
            script_division_json=json.dumps(division.model_dump(), ensure_ascii=False),
            consistency_json=json.dumps(consistency.model_dump(), ensure_ascii=False),
        )
        logger.info("Full process completed successfully")
        return success_response(data=final_result)

    except Exception as e:
        logger.error(f"Full process failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process script: {str(e)}"
        )

