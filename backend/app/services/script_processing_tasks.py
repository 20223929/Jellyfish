from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chains.agents import ScriptDividerAgent
from app.chains.agents.script_processing_agents import (
    EntityMergeResult,
    ScriptConsistencyCheckResult,
    ScriptDivisionResult,
    ScriptOptimizationResult,
    ScriptSimplificationResult,
    VariantAnalysisResult,
)
from app.schemas.skills.character_portrait import CharacterPortraitAnalysisResult
from app.schemas.skills.costume_info_analysis import CostumeInfoAnalysisResult
from app.schemas.skills.prop_info_analysis import PropInfoAnalysisResult
from app.schemas.skills.scene_info_analysis import SceneInfoAnalysisResult
from app.core.db import async_session_maker
from app.core.task_manager import DeliveryMode, SqlAlchemyTaskStore, TaskManager
from app.core.task_manager.types import TaskStatus
from app.dependencies import get_llm, get_nothinking_llm
from app.models.task import GenerationTask, GenerationTaskStatus
from app.models.task_links import GenerationTaskLink
from app.services.common import entity_not_found
from app.services.studio.script_division import write_division_result_to_chapter
from app.chains.agents import ConsistencyCheckerAgent, EntityMergerAgent, VariantAnalyzerAgent
from app.chains.agents import (
    CharacterPortraitAnalysisAgent,
    CostumeInfoAnalysisAgent,
    PropInfoAnalysisAgent,
    SceneInfoAnalysisAgent,
    ScriptOptimizerAgent,
    ScriptSimplifierAgent,
)


logger = logging.getLogger(__name__)

CHAPTER_DIVISION_RELATION_TYPE = "chapter_division"
SCRIPT_EXTRACTION_RELATION_TYPE = "script_extraction"
ENTITY_MERGE_RELATION_TYPE = "entity_merge"  # 预备能力：当前无真实前端入口
CONSISTENCY_CHECK_RELATION_TYPE = "consistency_check"
VARIANT_ANALYSIS_RELATION_TYPE = "variant_analysis"  # 预备能力：当前无真实前端入口
CHARACTER_PORTRAIT_ANALYSIS_RELATION_TYPE = "character_portrait_analysis"
PROP_INFO_ANALYSIS_RELATION_TYPE = "prop_info_analysis"
SCENE_INFO_ANALYSIS_RELATION_TYPE = "scene_info_analysis"
COSTUME_INFO_ANALYSIS_RELATION_TYPE = "costume_info_analysis"
SCRIPT_OPTIMIZATION_RELATION_TYPE = "script_optimization"
SCRIPT_SIMPLIFICATION_RELATION_TYPE = "script_simplification"
SCRIPT_DIVIDE_TASK_KIND = "script_divide"
SCRIPT_EXTRACT_TASK_KIND = "script_extract"
SCRIPT_MERGE_TASK_KIND = "script_merge"
SCRIPT_CONSISTENCY_TASK_KIND = "script_consistency"
SCRIPT_VARIANT_TASK_KIND = "script_variant"
SCRIPT_CHARACTER_PORTRAIT_TASK_KIND = "script_character_portrait"
SCRIPT_PROP_INFO_TASK_KIND = "script_prop_info"
SCRIPT_SCENE_INFO_TASK_KIND = "script_scene_info"
SCRIPT_COSTUME_INFO_TASK_KIND = "script_costume_info"
SCRIPT_OPTIMIZE_TASK_KIND = "script_optimize"
SCRIPT_SIMPLIFY_TASK_KIND = "script_simplify"
_ACTIVE_TASK_STATUSES = (
    GenerationTaskStatus.pending,
    GenerationTaskStatus.running,
    GenerationTaskStatus.streaming,
)


class _CreateOnlyTask:
    """仅用于 TaskManager.create，避免为异步任务额外声明无意义 task 类。"""

    async def run(self, *args: object, **kwargs: object):
        return None

    async def status(self) -> dict[str, object]:
        return {}

    async def is_done(self) -> bool:
        return False

    async def get_result(self) -> object:
        return None


@dataclass(slots=True)
class AsyncTaskCreateResult:
    task_id: str
    status: TaskStatus
    reused: bool
    relation_type: str
    relation_entity_id: str


async def _cancel_if_requested(
    store: SqlAlchemyTaskStore,
    task_id: str,
    db: AsyncSession,
) -> bool:
    """在阶段边界检查取消请求，并统一完成 cancelled 收尾。"""

    if not await store.is_cancel_requested(task_id):
        return False
    await store.mark_cancelled(task_id)
    await db.commit()
    return True


async def find_active_divide_task(
    db: AsyncSession,
    *,
    chapter_id: str,
) -> GenerationTask | None:
    stmt = (
        select(GenerationTask)
        .join(GenerationTaskLink, GenerationTaskLink.task_id == GenerationTask.id)
        .where(
            GenerationTaskLink.relation_type == CHAPTER_DIVISION_RELATION_TYPE,
            GenerationTaskLink.relation_entity_id == chapter_id,
            GenerationTask.status.in_(_ACTIVE_TASK_STATUSES),
        )
        .order_by(GenerationTask.updated_at.desc(), GenerationTask.id.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()


async def create_divide_task(
    db: AsyncSession,
    *,
    chapter_id: str,
    script_text: str,
    write_to_db: bool,
) -> AsyncTaskCreateResult:
    existing = await find_active_divide_task(db, chapter_id=chapter_id)
    if existing is not None:
        status_value = existing.status.value if hasattr(existing.status, "value") else str(existing.status)
        return AsyncTaskCreateResult(
            task_id=existing.id,
            status=TaskStatus(status_value),
            reused=True,
            relation_type=CHAPTER_DIVISION_RELATION_TYPE,
            relation_entity_id=chapter_id,
        )

    store = SqlAlchemyTaskStore(db)
    tm = TaskManager(store=store, strategies={})
    run_args = {
        "chapter_id": chapter_id,
        "script_text": script_text,
        "write_to_db": write_to_db,
    }
    task_record = await tm.create(
        task=_CreateOnlyTask(),
        mode=DeliveryMode.async_polling,
        task_kind=SCRIPT_DIVIDE_TASK_KIND,
        run_args=run_args,
    )
    db.add(
        GenerationTaskLink(
            task_id=task_record.id,
            resource_type="task_link",
            relation_type=CHAPTER_DIVISION_RELATION_TYPE,
            relation_entity_id=chapter_id,
        )
    )
    await db.flush()

    return AsyncTaskCreateResult(
        task_id=task_record.id,
        status=task_record.status,
        reused=False,
        relation_type=CHAPTER_DIVISION_RELATION_TYPE,
        relation_entity_id=chapter_id,
    )


async def run_divide_task(task_id: str) -> None:
    """后台执行章节分镜提取任务。

    说明：
    - 这里先做“协作式取消”，在关键阶段检查取消请求。
    - 当前单次 LLM 调用仍无法保证即时硬中断，因此只在阶段边界停下。
    """

    async with async_session_maker() as db:
        store = SqlAlchemyTaskStore(db)
        task = await store.get(task_id)
        if task is None:
            logger.warning("divide task not found: %s", task_id)
            return

        if await _cancel_if_requested(store, task_id, db):
            return

        await store.set_status(task_id, TaskStatus.running)
        await store.set_progress(task_id, 5)
        await db.commit()

        run_args = task.payload.get("run_args") or {}
        script_text = str(run_args.get("script_text") or "")
        chapter_id = str(run_args.get("chapter_id") or "")
        write_to_db = bool(run_args.get("write_to_db"))

    try:
        async with async_session_maker() as db:
            llm = await get_nothinking_llm(db)
            store = SqlAlchemyTaskStore(db)
            if await _cancel_if_requested(store, task_id, db):
                return

            agent = ScriptDividerAgent(llm)
            result: ScriptDivisionResult = agent.divide_script(script_text=script_text)
            await store.set_progress(task_id, 70)
            await store.set_result(task_id, result.model_dump())
            await db.commit()

        async with async_session_maker() as db:
            store = SqlAlchemyTaskStore(db)
            if await _cancel_if_requested(store, task_id, db):
                return

            if write_to_db:
                if not chapter_id:
                    raise HTTPException(status_code=400, detail="chapter_id is required for write_to_db=true")
                await write_division_result_to_chapter(db, chapter_id=chapter_id, result=result)

            await store.set_progress(task_id, 100)
            await store.set_status(task_id, TaskStatus.succeeded)
            await db.commit()
    except HTTPException as exc:
        async with async_session_maker() as db:
            store = SqlAlchemyTaskStore(db)
            await store.set_error(task_id, exc.detail if isinstance(exc.detail, str) else str(exc.detail))
            await store.set_status(task_id, TaskStatus.failed)
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.exception("divide task failed: %s", task_id)
        async with async_session_maker() as db:
            store = SqlAlchemyTaskStore(db)
            await store.set_error(task_id, str(exc))
            await store.set_status(task_id, TaskStatus.failed)
            await db.commit()


def spawn_divide_task(task_id: str) -> None:
    """统一封装后台启动：第一阶段改为通用 Celery 执行入口。"""
    from app.tasks.execute_task import enqueue_task_execution

    enqueue_task_execution(task_id)


async def find_active_extract_task(
    db: AsyncSession,
    *,
    chapter_id: str,
) -> GenerationTask | None:
    stmt = (
        select(GenerationTask)
        .join(GenerationTaskLink, GenerationTaskLink.task_id == GenerationTask.id)
        .where(
            GenerationTaskLink.relation_type == SCRIPT_EXTRACTION_RELATION_TYPE,
            GenerationTaskLink.relation_entity_id == chapter_id,
            GenerationTask.status.in_(_ACTIVE_TASK_STATUSES),
        )
        .order_by(GenerationTask.updated_at.desc(), GenerationTask.id.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()


async def find_active_merge_task(
    db: AsyncSession,
    *,
    relation_entity_id: str,
) -> GenerationTask | None:
    stmt = (
        select(GenerationTask)
        .join(GenerationTaskLink, GenerationTaskLink.task_id == GenerationTask.id)
        .where(
            GenerationTaskLink.relation_type == ENTITY_MERGE_RELATION_TYPE,
            GenerationTaskLink.relation_entity_id == relation_entity_id,
            GenerationTask.status.in_(_ACTIVE_TASK_STATUSES),
        )
        .order_by(GenerationTask.updated_at.desc(), GenerationTask.id.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()


async def find_active_consistency_task(
    db: AsyncSession,
    *,
    relation_entity_id: str,
) -> GenerationTask | None:
    stmt = (
        select(GenerationTask)
        .join(GenerationTaskLink, GenerationTaskLink.task_id == GenerationTask.id)
        .where(
            GenerationTaskLink.relation_type == CONSISTENCY_CHECK_RELATION_TYPE,
            GenerationTaskLink.relation_entity_id == relation_entity_id,
            GenerationTask.status.in_(_ACTIVE_TASK_STATUSES),
        )
        .order_by(GenerationTask.updated_at.desc(), GenerationTask.id.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()


async def find_active_variant_task(
    db: AsyncSession,
    *,
    relation_entity_id: str,
) -> GenerationTask | None:
    stmt = (
        select(GenerationTask)
        .join(GenerationTaskLink, GenerationTaskLink.task_id == GenerationTask.id)
        .where(
            GenerationTaskLink.relation_type == VARIANT_ANALYSIS_RELATION_TYPE,
            GenerationTaskLink.relation_entity_id == relation_entity_id,
            GenerationTask.status.in_(_ACTIVE_TASK_STATUSES),
        )
        .order_by(GenerationTask.updated_at.desc(), GenerationTask.id.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()


async def _find_active_analysis_task(
    db: AsyncSession,
    *,
    relation_type: str,
    relation_entity_id: str,
) -> GenerationTask | None:
    stmt = (
        select(GenerationTask)
        .join(GenerationTaskLink, GenerationTaskLink.task_id == GenerationTask.id)
        .where(
            GenerationTaskLink.relation_type == relation_type,
            GenerationTaskLink.relation_entity_id == relation_entity_id,
            GenerationTask.status.in_(_ACTIVE_TASK_STATUSES),
        )
        .order_by(GenerationTask.updated_at.desc(), GenerationTask.id.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()


def pick_merge_relation_entity_id(*, chapter_id: str | None, project_id: str | None) -> str:
    relation_entity_id = (chapter_id or "").strip() or (project_id or "").strip()
    if not relation_entity_id:
        raise HTTPException(status_code=400, detail="chapter_id or project_id is required for merge-entities-async")
    return relation_entity_id


def pick_consistency_relation_entity_id(*, chapter_id: str | None, project_id: str | None) -> str:
    relation_entity_id = (chapter_id or "").strip() or (project_id or "").strip()
    if not relation_entity_id:
        raise HTTPException(status_code=400, detail="chapter_id or project_id is required for check-consistency-async")
    return relation_entity_id


def pick_variant_relation_entity_id(*, chapter_id: str | None, project_id: str | None) -> str:
    relation_entity_id = (chapter_id or "").strip() or (project_id or "").strip()
    if not relation_entity_id:
        raise HTTPException(status_code=400, detail="chapter_id or project_id is required for analyze-variants-async")
    return relation_entity_id


def pick_analysis_relation_entity_id(
    *,
    relation_entity_id: str | None = None,
    chapter_id: str | None,
    project_id: str | None,
    endpoint: str,
) -> str:
    relation_entity_id = (relation_entity_id or "").strip() or (chapter_id or "").strip() or (project_id or "").strip()
    if not relation_entity_id:
        raise HTTPException(status_code=400, detail=f"relation_entity_id or chapter_id or project_id is required for {endpoint}")
    return relation_entity_id


async def create_extract_task(
    db: AsyncSession,
    *,
    project_id: str,
    chapter_id: str,
    script_division: dict,
    consistency: dict | None,
    refresh_cache: bool,
) -> AsyncTaskCreateResult:
    existing = await find_active_extract_task(db, chapter_id=chapter_id)
    if existing is not None:
        status_value = existing.status.value if hasattr(existing.status, "value") else str(existing.status)
        return AsyncTaskCreateResult(
            task_id=existing.id,
            status=TaskStatus(status_value),
            reused=True,
            relation_type=SCRIPT_EXTRACTION_RELATION_TYPE,
            relation_entity_id=chapter_id,
        )

    store = SqlAlchemyTaskStore(db)
    tm = TaskManager(store=store, strategies={})
    run_args = {
        "project_id": project_id,
        "chapter_id": chapter_id,
        "script_division": script_division,
        "consistency": consistency,
        "refresh_cache": refresh_cache,
    }
    task_record = await tm.create(
        task=_CreateOnlyTask(),
        mode=DeliveryMode.async_polling,
        task_kind=SCRIPT_EXTRACT_TASK_KIND,
        run_args=run_args,
    )
    db.add(
        GenerationTaskLink(
            task_id=task_record.id,
            resource_type="task_link",
            relation_type=SCRIPT_EXTRACTION_RELATION_TYPE,
            relation_entity_id=chapter_id,
        )
    )
    await db.flush()
    return AsyncTaskCreateResult(
        task_id=task_record.id,
        status=task_record.status,
        reused=False,
        relation_type=SCRIPT_EXTRACTION_RELATION_TYPE,
        relation_entity_id=chapter_id,
    )


async def create_merge_task(
    db: AsyncSession,
    *,
    relation_entity_id: str,
    all_shot_extractions: list[dict],
    historical_library: dict | None,
    script_division: dict | None,
    previous_merge: dict | None,
    conflict_resolutions: list[dict] | None,
) -> AsyncTaskCreateResult:
    existing = await find_active_merge_task(db, relation_entity_id=relation_entity_id)
    if existing is not None:
        status_value = existing.status.value if hasattr(existing.status, "value") else str(existing.status)
        return AsyncTaskCreateResult(
            task_id=existing.id,
            status=TaskStatus(status_value),
            reused=True,
            relation_type=ENTITY_MERGE_RELATION_TYPE,
            relation_entity_id=relation_entity_id,
        )

    store = SqlAlchemyTaskStore(db)
    tm = TaskManager(store=store, strategies={})
    run_args = {
        "all_shot_extractions": all_shot_extractions,
        "historical_library": historical_library,
        "script_division": script_division,
        "previous_merge": previous_merge,
        "conflict_resolutions": conflict_resolutions,
    }
    task_record = await tm.create(
        task=_CreateOnlyTask(),
        mode=DeliveryMode.async_polling,
        task_kind=SCRIPT_MERGE_TASK_KIND,
        run_args=run_args,
    )
    db.add(
        GenerationTaskLink(
            task_id=task_record.id,
            resource_type="task_link",
            relation_type=ENTITY_MERGE_RELATION_TYPE,
            relation_entity_id=relation_entity_id,
        )
    )
    await db.flush()
    return AsyncTaskCreateResult(
        task_id=task_record.id,
        status=task_record.status,
        reused=False,
        relation_type=ENTITY_MERGE_RELATION_TYPE,
        relation_entity_id=relation_entity_id,
    )


async def create_consistency_task(
    db: AsyncSession,
    *,
    relation_entity_id: str,
    script_text: str,
) -> AsyncTaskCreateResult:
    existing = await find_active_consistency_task(db, relation_entity_id=relation_entity_id)
    if existing is not None:
        status_value = existing.status.value if hasattr(existing.status, "value") else str(existing.status)
        return AsyncTaskCreateResult(
            task_id=existing.id,
            status=TaskStatus(status_value),
            reused=True,
            relation_type=CONSISTENCY_CHECK_RELATION_TYPE,
            relation_entity_id=relation_entity_id,
        )

    store = SqlAlchemyTaskStore(db)
    tm = TaskManager(store=store, strategies={})
    task_record = await tm.create(
        task=_CreateOnlyTask(),
        mode=DeliveryMode.async_polling,
        task_kind=SCRIPT_CONSISTENCY_TASK_KIND,
        run_args={"script_text": script_text},
    )
    db.add(
        GenerationTaskLink(
            task_id=task_record.id,
            resource_type="task_link",
            relation_type=CONSISTENCY_CHECK_RELATION_TYPE,
            relation_entity_id=relation_entity_id,
        )
    )
    await db.flush()
    return AsyncTaskCreateResult(
        task_id=task_record.id,
        status=task_record.status,
        reused=False,
        relation_type=CONSISTENCY_CHECK_RELATION_TYPE,
        relation_entity_id=relation_entity_id,
    )


async def create_variant_task(
    db: AsyncSession,
    *,
    relation_entity_id: str,
    merged_library: dict,
    all_shot_extractions: list[dict],
    script_division: dict | None,
) -> AsyncTaskCreateResult:
    existing = await find_active_variant_task(db, relation_entity_id=relation_entity_id)
    if existing is not None:
        status_value = existing.status.value if hasattr(existing.status, "value") else str(existing.status)
        return AsyncTaskCreateResult(
            task_id=existing.id,
            status=TaskStatus(status_value),
            reused=True,
            relation_type=VARIANT_ANALYSIS_RELATION_TYPE,
            relation_entity_id=relation_entity_id,
        )

    store = SqlAlchemyTaskStore(db)
    tm = TaskManager(store=store, strategies={})
    task_record = await tm.create(
        task=_CreateOnlyTask(),
        mode=DeliveryMode.async_polling,
        task_kind=SCRIPT_VARIANT_TASK_KIND,
        run_args={
            "merged_library": merged_library,
            "all_shot_extractions": all_shot_extractions,
            "script_division": script_division,
        },
    )
    db.add(
        GenerationTaskLink(
            task_id=task_record.id,
            resource_type="task_link",
            relation_type=VARIANT_ANALYSIS_RELATION_TYPE,
            relation_entity_id=relation_entity_id,
        )
    )
    await db.flush()
    return AsyncTaskCreateResult(
        task_id=task_record.id,
        status=task_record.status,
        reused=False,
        relation_type=VARIANT_ANALYSIS_RELATION_TYPE,
        relation_entity_id=relation_entity_id,
    )


async def _create_analysis_task(
    db: AsyncSession,
    *,
    task_kind: str,
    relation_type: str,
    relation_entity_id: str,
    run_args: dict,
) -> AsyncTaskCreateResult:
    existing = await _find_active_analysis_task(db, relation_type=relation_type, relation_entity_id=relation_entity_id)
    if existing is not None:
        status_value = existing.status.value if hasattr(existing.status, "value") else str(existing.status)
        return AsyncTaskCreateResult(
            task_id=existing.id,
            status=TaskStatus(status_value),
            reused=True,
            relation_type=relation_type,
            relation_entity_id=relation_entity_id,
        )

    store = SqlAlchemyTaskStore(db)
    tm = TaskManager(store=store, strategies={})
    task_record = await tm.create(
        task=_CreateOnlyTask(),
        mode=DeliveryMode.async_polling,
        task_kind=task_kind,
        run_args=run_args,
    )
    db.add(
        GenerationTaskLink(
            task_id=task_record.id,
            resource_type="task_link",
            relation_type=relation_type,
            relation_entity_id=relation_entity_id,
        )
    )
    await db.flush()
    return AsyncTaskCreateResult(
        task_id=task_record.id,
        status=task_record.status,
        reused=False,
        relation_type=relation_type,
        relation_entity_id=relation_entity_id,
    )


async def create_character_portrait_task(
    db: AsyncSession,
    *,
    relation_entity_id: str,
    character_context: str | None,
    character_description: str,
) -> AsyncTaskCreateResult:
    return await _create_analysis_task(
        db,
        task_kind=SCRIPT_CHARACTER_PORTRAIT_TASK_KIND,
        relation_type=CHARACTER_PORTRAIT_ANALYSIS_RELATION_TYPE,
        relation_entity_id=relation_entity_id,
        run_args={
            "character_context": character_context,
            "character_description": character_description,
        },
    )


async def create_prop_info_task(
    db: AsyncSession,
    *,
    relation_entity_id: str,
    prop_context: str | None,
    prop_description: str,
) -> AsyncTaskCreateResult:
    return await _create_analysis_task(
        db,
        task_kind=SCRIPT_PROP_INFO_TASK_KIND,
        relation_type=PROP_INFO_ANALYSIS_RELATION_TYPE,
        relation_entity_id=relation_entity_id,
        run_args={
            "prop_context": prop_context,
            "prop_description": prop_description,
        },
    )


async def create_scene_info_task(
    db: AsyncSession,
    *,
    relation_entity_id: str,
    scene_context: str | None,
    scene_description: str,
) -> AsyncTaskCreateResult:
    return await _create_analysis_task(
        db,
        task_kind=SCRIPT_SCENE_INFO_TASK_KIND,
        relation_type=SCENE_INFO_ANALYSIS_RELATION_TYPE,
        relation_entity_id=relation_entity_id,
        run_args={
            "scene_context": scene_context,
            "scene_description": scene_description,
        },
    )


async def create_costume_info_task(
    db: AsyncSession,
    *,
    relation_entity_id: str,
    costume_context: str | None,
    costume_description: str,
) -> AsyncTaskCreateResult:
    return await _create_analysis_task(
        db,
        task_kind=SCRIPT_COSTUME_INFO_TASK_KIND,
        relation_type=COSTUME_INFO_ANALYSIS_RELATION_TYPE,
        relation_entity_id=relation_entity_id,
        run_args={
            "costume_context": costume_context,
            "costume_description": costume_description,
        },
    )


async def create_script_optimization_task(
    db: AsyncSession,
    *,
    relation_entity_id: str,
    script_text: str,
    consistency: dict,
) -> AsyncTaskCreateResult:
    return await _create_analysis_task(
        db,
        task_kind=SCRIPT_OPTIMIZE_TASK_KIND,
        relation_type=SCRIPT_OPTIMIZATION_RELATION_TYPE,
        relation_entity_id=relation_entity_id,
        run_args={
            "script_text": script_text,
            "consistency": consistency,
        },
    )


async def create_script_simplification_task(
    db: AsyncSession,
    *,
    relation_entity_id: str,
    script_text: str,
) -> AsyncTaskCreateResult:
    return await _create_analysis_task(
        db,
        task_kind=SCRIPT_SIMPLIFY_TASK_KIND,
        relation_type=SCRIPT_SIMPLIFICATION_RELATION_TYPE,
        relation_entity_id=relation_entity_id,
        run_args={
            "script_text": script_text,
        },
    )


def spawn_extract_task(task_id: str) -> None:
    from app.tasks.execute_task import enqueue_task_execution

    enqueue_task_execution(task_id)


async def run_merge_task(task_id: str) -> None:
    async with async_session_maker() as db:
        store = SqlAlchemyTaskStore(db)
        task = await store.get(task_id)
        if task is None:
            logger.warning("merge task not found: %s", task_id)
            return

        if await _cancel_if_requested(store, task_id, db):
            return

        await store.set_status(task_id, TaskStatus.running)
        await store.set_progress(task_id, 5)
        await db.commit()
        run_args = task.payload.get("run_args") or {}

    try:
        async with async_session_maker() as db:
            store = SqlAlchemyTaskStore(db)
            if await _cancel_if_requested(store, task_id, db):
                return

            llm = await get_llm(db)
            agent = EntityMergerAgent(llm)
            result: EntityMergeResult = agent.extract(
                all_extractions_json=json.dumps(run_args.get("all_shot_extractions") or [], ensure_ascii=False),
                historical_library_json=json.dumps(run_args.get("historical_library") or {}, ensure_ascii=False),
                script_division_json=json.dumps(run_args.get("script_division") or {}, ensure_ascii=False),
                previous_merge_json=json.dumps(run_args.get("previous_merge") or {}, ensure_ascii=False),
                conflict_resolutions_json=json.dumps(run_args.get("conflict_resolutions") or [], ensure_ascii=False),
            )
            await store.set_progress(task_id, 100)
            await store.set_result(task_id, result.model_dump())
            if await _cancel_if_requested(store, task_id, db):
                return
            await store.set_status(task_id, TaskStatus.succeeded)
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.exception("merge task failed: %s", task_id)
        async with async_session_maker() as db:
            store = SqlAlchemyTaskStore(db)
            await store.set_error(task_id, str(exc))
            await store.set_status(task_id, TaskStatus.failed)
            await db.commit()


def spawn_merge_task(task_id: str) -> None:
    asyncio.create_task(run_merge_task(task_id))


async def run_consistency_task(task_id: str) -> None:
    async with async_session_maker() as db:
        store = SqlAlchemyTaskStore(db)
        task = await store.get(task_id)
        if task is None:
            logger.warning("consistency task not found: %s", task_id)
            return

        if await _cancel_if_requested(store, task_id, db):
            return

        await store.set_status(task_id, TaskStatus.running)
        await store.set_progress(task_id, 5)
        await db.commit()
        run_args = task.payload.get("run_args") or {}

    try:
        async with async_session_maker() as db:
            store = SqlAlchemyTaskStore(db)
            if await _cancel_if_requested(store, task_id, db):
                return

            llm = await get_llm(db)
            agent = ConsistencyCheckerAgent(llm)
            result: ScriptConsistencyCheckResult = agent.extract(script_text=str(run_args.get("script_text") or ""))
            await store.set_progress(task_id, 100)
            await store.set_result(task_id, result.model_dump())
            if await _cancel_if_requested(store, task_id, db):
                return
            await store.set_status(task_id, TaskStatus.succeeded)
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.exception("consistency task failed: %s", task_id)
        async with async_session_maker() as db:
            store = SqlAlchemyTaskStore(db)
            await store.set_error(task_id, str(exc))
            await store.set_status(task_id, TaskStatus.failed)
            await db.commit()


def spawn_consistency_task(task_id: str) -> None:
    from app.tasks.execute_task import enqueue_task_execution

    enqueue_task_execution(task_id)


async def run_variant_task(task_id: str) -> None:
    async with async_session_maker() as db:
        store = SqlAlchemyTaskStore(db)
        task = await store.get(task_id)
        if task is None:
            logger.warning("variant task not found: %s", task_id)
            return

        if await _cancel_if_requested(store, task_id, db):
            return

        await store.set_status(task_id, TaskStatus.running)
        await store.set_progress(task_id, 5)
        await db.commit()
        run_args = task.payload.get("run_args") or {}

    try:
        async with async_session_maker() as db:
            store = SqlAlchemyTaskStore(db)
            if await _cancel_if_requested(store, task_id, db):
                return

            llm = await get_llm(db)
            agent = VariantAnalyzerAgent(llm)
            result: VariantAnalysisResult = agent.extract(
                merged_library_json=json.dumps(run_args.get("merged_library") or {}, ensure_ascii=False),
                all_extractions_json=json.dumps(run_args.get("all_shot_extractions") or [], ensure_ascii=False),
                script_division_json=json.dumps(run_args.get("script_division") or {}, ensure_ascii=False),
            )
            await store.set_progress(task_id, 100)
            await store.set_result(task_id, result.model_dump())
            if await _cancel_if_requested(store, task_id, db):
                return
            await store.set_status(task_id, TaskStatus.succeeded)
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.exception("variant task failed: %s", task_id)
        async with async_session_maker() as db:
            store = SqlAlchemyTaskStore(db)
            await store.set_error(task_id, str(exc))
            await store.set_status(task_id, TaskStatus.failed)
            await db.commit()


def spawn_variant_task(task_id: str) -> None:
    asyncio.create_task(run_variant_task(task_id))


async def _run_simple_analysis_task(
    task_id: str,
    *,
    agent_factory,
    run_analysis,
) -> None:
    async with async_session_maker() as db:
        store = SqlAlchemyTaskStore(db)
        task = await store.get(task_id)
        if task is None:
            logger.warning("analysis task not found: %s", task_id)
            return

        if await _cancel_if_requested(store, task_id, db):
            return

        await store.set_status(task_id, TaskStatus.running)
        await store.set_progress(task_id, 5)
        await db.commit()
        run_args = task.payload.get("run_args") or {}

    try:
        async with async_session_maker() as db:
            store = SqlAlchemyTaskStore(db)
            if await _cancel_if_requested(store, task_id, db):
                return

            llm = await get_llm(db)
            agent = agent_factory(llm)
            result = run_analysis(agent, run_args)
            await store.set_progress(task_id, 100)
            await store.set_result(task_id, result.model_dump())
            if await _cancel_if_requested(store, task_id, db):
                return
            await store.set_status(task_id, TaskStatus.succeeded)
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.exception("analysis task failed: %s", task_id)
        async with async_session_maker() as db:
            store = SqlAlchemyTaskStore(db)
            await store.set_error(task_id, str(exc))
            await store.set_status(task_id, TaskStatus.failed)
            await db.commit()


async def run_character_portrait_task(task_id: str) -> None:
    await _run_simple_analysis_task(
        task_id,
        agent_factory=CharacterPortraitAnalysisAgent,
        run_analysis=lambda agent, args: agent.analyze_character_description(
            character_context=args.get("character_context"),
            character_description=str(args.get("character_description") or ""),
        ),
    )


async def run_prop_info_task(task_id: str) -> None:
    await _run_simple_analysis_task(
        task_id,
        agent_factory=PropInfoAnalysisAgent,
        run_analysis=lambda agent, args: agent.analyze_prop_description(
            prop_context=args.get("prop_context"),
            prop_description=str(args.get("prop_description") or ""),
        ),
    )


async def run_scene_info_task(task_id: str) -> None:
    await _run_simple_analysis_task(
        task_id,
        agent_factory=SceneInfoAnalysisAgent,
        run_analysis=lambda agent, args: agent.analyze_scene_description(
            scene_context=args.get("scene_context"),
            scene_description=str(args.get("scene_description") or ""),
        ),
    )


async def run_costume_info_task(task_id: str) -> None:
    await _run_simple_analysis_task(
        task_id,
        agent_factory=CostumeInfoAnalysisAgent,
        run_analysis=lambda agent, args: agent.analyze_costume_description(
            costume_context=args.get("costume_context"),
            costume_description=str(args.get("costume_description") or ""),
        ),
    )


def spawn_character_portrait_task(task_id: str) -> None:
    from app.tasks.execute_task import enqueue_task_execution

    enqueue_task_execution(task_id)


def spawn_prop_info_task(task_id: str) -> None:
    from app.tasks.execute_task import enqueue_task_execution

    enqueue_task_execution(task_id)


def spawn_scene_info_task(task_id: str) -> None:
    from app.tasks.execute_task import enqueue_task_execution

    enqueue_task_execution(task_id)


def spawn_costume_info_task(task_id: str) -> None:
    from app.tasks.execute_task import enqueue_task_execution

    enqueue_task_execution(task_id)


async def run_script_optimization_task(task_id: str) -> None:
    async def _runner(llm, run_args: dict) -> ScriptOptimizationResult:
        agent = ScriptOptimizerAgent(llm)
        return agent.extract(
            script_text=str(run_args.get("script_text") or ""),
            consistency_json=json.dumps(dict(run_args.get("consistency") or {}), ensure_ascii=False),
        )

    await _run_simple_analysis_task(task_id, task_runner=_runner)


async def run_script_simplification_task(task_id: str) -> None:
    async def _runner(llm, run_args: dict) -> ScriptSimplificationResult:
        agent = ScriptSimplifierAgent(llm)
        return agent.extract(script_text=str(run_args.get("script_text") or ""))

    await _run_simple_analysis_task(task_id, task_runner=_runner)


def spawn_script_optimization_task(task_id: str) -> None:
    from app.tasks.execute_task import enqueue_task_execution

    enqueue_task_execution(task_id)


def spawn_script_simplification_task(task_id: str) -> None:
    from app.tasks.execute_task import enqueue_task_execution

    enqueue_task_execution(task_id)
