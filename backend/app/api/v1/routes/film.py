"""影视技能 API：实体抽取、分镜抽取。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from app.core.skills_runtime import (
    FilmEntityExtractor,
    FilmShotlistStoryboarder,
    FilmEntityExtractionResult,
    FilmShotlistResult,
)
from app.dependencies import get_llm

router = APIRouter()

# ---------- 请求体 ----------


class TextChunkInput(BaseModel):
    """单个文本块。"""

    chunk_id: str = Field(..., description="块 ID，如 chapter1_p03")
    text: str = Field(..., description="原文内容")


class EntityExtractRequest(BaseModel):
    """实体抽取请求。"""

    source_id: str = Field(..., description="小说/章节标识，如 novel_ch01")
    language: str | None = Field(None, description="语言，如 zh / en")
    chunks: list[TextChunkInput] = Field(..., description="文本块列表")


class ShotlistExtractRequest(BaseModel):
    """分镜抽取请求。"""

    source_id: str = Field(..., description="小说/章节标识")
    source_title: str | None = Field(None, description="书名/章节名")
    language: str | None = Field(None, description="语言，如 zh / en")
    chunks: list[TextChunkInput] = Field(..., description="文本块列表")


# ---------- 端点 ----------


@router.post(
    "/extract/entities",
    response_model=FilmEntityExtractionResult,
    summary="关键信息抽取",
    description="从小说文本中抽取人物、地点、道具，忠实原文、可追溯证据。",
)
def extract_entities(
    body: EntityExtractRequest,
    llm: Runnable = Depends(get_llm),
) -> FilmEntityExtractionResult:
    """FilmEntityExtractor：人物/地点/道具抽取。"""
    extractor = FilmEntityExtractor(llm)
    extractor.load_skill("film_entity_extractor")
    chunks_json = json.dumps(
        [{"chunk_id": c.chunk_id, "text": c.text} for c in body.chunks],
        ensure_ascii=False,
    )
    return extractor.extract(
        {
            "source_id": body.source_id,
            "language": body.language or "zh",
            "chunks_json": chunks_json,
        }
    )


@router.post(
    "/extract/shotlist",
    response_model=FilmShotlistResult,
    summary="分镜抽取",
    description="将小说片段转为可拍镜头表（景别/机位/运镜/转场/VFX）。",
)
def extract_shotlist(
    body: ShotlistExtractRequest,
    llm: Runnable = Depends(get_llm),
) -> FilmShotlistResult:
    """FilmShotlistStoryboarder：场景/镜头/转场抽取。"""
    storyboarder = FilmShotlistStoryboarder(llm)
    storyboarder.load_skill("film_shotlist")
    chunks_json = json.dumps(
        [{"chunk_id": c.chunk_id, "text": c.text} for c in body.chunks],
        ensure_ascii=False,
    )
    return storyboarder.extract(
        {
            "source_id": body.source_id,
            "source_title": body.source_title or "",
            "language": body.language or "zh",
            "chunks_json": chunks_json,
        }
    )
